import base64
import io
import os
import socket
import concurrent.futures
import time
import threading

import pytest
import json

from ansible_runner import run
from ansible_runner.streaming import Transmitter, Worker, Processor

import ansible_runner.interface  # AWX import pattern


class TestStreamingUsage:

    @pytest.fixture(autouse=True)
    def reset_self_props(self):
        self.status_data = None

    def status_handler(self, status_data, runner_config=None):
        self.status_data = status_data

    def get_job_kwargs(self, job_type):
        """For this test scenaro, the ansible-runner interface kwargs"""
        if job_type == 'run':
            job_kwargs = dict(playbook='debug.yml')
        else:
            job_kwargs = dict(module='setup', host_pattern='localhost')
        # also test use of user env vars
        job_kwargs['envvars'] = dict(MY_ENV_VAR='bogus')
        return job_kwargs

    @staticmethod
    def get_stdout(process_dir):
        events_dir = os.path.join(process_dir, 'artifacts', 'job_events')
        events = []
        for file in os.listdir(events_dir):
            with open(os.path.join(events_dir, file), 'r') as f:
                if file in ('status', 'rc'):
                    continue
                content = f.read()
                events.append(json.loads(content))
        return '\n'.join(event['stdout'] for event in events)

    @staticmethod
    def check_artifacts(process_dir, job_type):

        assert set(os.listdir(process_dir)) == {'artifacts', }

        stdout = TestStreamingUsage.get_stdout(process_dir)

        if job_type == 'run':
            assert 'Hello world!' in stdout
        else:
            assert '"ansible_facts"' in stdout

    @pytest.mark.parametrize("job_type", ['run', 'adhoc'])
    def test_remote_job_interface(self, tmp_path, project_fixtures, job_type):
        transmit_dir = project_fixtures / 'debug'
        worker_dir = tmp_path / 'for_worker'
        worker_dir.mkdir()

        process_dir = tmp_path / 'for_process'
        process_dir.mkdir()

        job_kwargs = self.get_job_kwargs(job_type)

        outgoing_buffer_file = tmp_path / 'buffer_out'
        outgoing_buffer_file.touch()
        outgoing_buffer = outgoing_buffer_file.open('b+r')

        transmitter = Transmitter(_output=outgoing_buffer, private_data_dir=transmit_dir, **job_kwargs)

        for key, value in job_kwargs.items():
            assert transmitter.kwargs.get(key, '') == value

        status, rc = transmitter.run()
        assert rc in (None, 0)
        assert status == 'unstarted'

        outgoing_buffer.seek(0)
        sent = outgoing_buffer.read()
        assert sent  # should not be blank at least
        assert b'zipfile' in sent

        incoming_buffer_file = tmp_path / 'buffer_in'
        incoming_buffer_file.touch()
        incoming_buffer = incoming_buffer_file.open('b+r')

        outgoing_buffer.seek(0)

        worker = Worker(_input=outgoing_buffer, _output=incoming_buffer, private_data_dir=worker_dir)
        worker.run()

        outgoing_buffer.seek(0)
        assert set(os.listdir(worker_dir)) == {'artifacts', 'inventory', 'project', 'env'}, outgoing_buffer.read()

        incoming_buffer.seek(0)  # again, be kind, rewind

        processor = Processor(_input=incoming_buffer, private_data_dir=process_dir)
        processor.run()

        self.check_artifacts(str(process_dir), job_type)

    @pytest.mark.parametrize("keepalive_setting", [
        0,  # keepalive explicitly disabled, default
        1,  # emit keepalives every 1s
        0.000000001,  # emit keepalives on a ridiculously small interval to test for output corruption
        None,  # default disable, test sets envvar for keepalives
    ])
    def test_keepalive_setting(self, tmp_path, project_fixtures, keepalive_setting):
        verbosity = None
        output_corruption_test_mode = 0 < (keepalive_setting or 0) < 1

        if output_corruption_test_mode:
            verbosity = 5
            # FIXME: turn on debug output too just to really spam the thing

        if keepalive_setting is None:
            # test the envvar fallback
            os.environ['ANSIBLE_RUNNER_KEEPALIVE_SECONDS'] = '1'
        elif 'ANSIBLE_RUNNER_KEEPALIVE_SECONDS' in os.environ:
            # don't allow this envvar to affect the test behavior
            del os.environ['ANSIBLE_RUNNER_KEEPALIVE_SECONDS']

        worker_dir = tmp_path / 'for_worker'
        process_dir = tmp_path / 'for_process'
        for dir in (worker_dir, process_dir):
            dir.mkdir()

        outgoing_buffer = io.BytesIO()
        incoming_buffer = io.BytesIO()
        for buffer in (outgoing_buffer, incoming_buffer):
            buffer.name = 'foo'

        status, rc = Transmitter(
            _output=outgoing_buffer, private_data_dir=project_fixtures / 'sleep',
            playbook='sleep.yml', extravars=dict(sleep_interval=2), verbosity=verbosity
        ).run()
        assert rc in (None, 0)
        assert status == 'unstarted'
        outgoing_buffer.seek(0)

        worker_start_time = time.time()

        worker = Worker(
            _input=outgoing_buffer, _output=incoming_buffer, private_data_dir=worker_dir,
            keepalive_seconds=keepalive_setting
        )
        worker.run()

        assert time.time() - worker_start_time > 2.0  # task sleeps for 2 second
        assert isinstance(worker._keepalive_thread, threading.Thread)  # we currently always create and start the thread
        assert worker._keepalive_thread.daemon
        worker._keepalive_thread.join(2)  # wait a couple of keepalive intervals to avoid exit race
        assert not worker._keepalive_thread.is_alive()  # make sure it's dead

        incoming_buffer.seek(0)
        Processor(_input=incoming_buffer, private_data_dir=process_dir).run()

        stdout = self.get_stdout(process_dir)
        assert 'Sleep for a specified interval' in stdout
        assert '"event": "keepalive"' not in stdout

        incoming_data = incoming_buffer.getvalue().decode('utf-8')
        if keepalive_setting == 0:
            assert incoming_data.count('"event": "keepalive"') == 0
        elif 0 < (keepalive_setting or 0) < 1:
            # JSON-load every line to ensure no interleaved keepalive output corruption
            line = None
            try:
                pending_payload_length = 0
                for line in incoming_data.splitlines():
                    if pending_payload_length:
                        # decode and check length to validate that we didn't trash the payload
                        # zap the mashed eof message from the end if present
                        line = line.rsplit('{"eof": true}', 1)[0]  # FUTURE: change this to removesuffix for 3.9+
                        assert pending_payload_length == len(base64.b64decode(line))
                        pending_payload_length = 0  # back to normal
                        continue

                    data = json.loads(line)
                    pending_payload_length = data.get('zipfile', 0)
            except json.JSONDecodeError:
                pytest.fail(f'unparseable JSON in output (likely corrupted by keepalive): {line}')
        else:
            # account for some wobble in the number of keepalives for artifact gather, etc
            assert 1 <= incoming_data.count('"event": "keepalive"') < 5

    @pytest.mark.parametrize("job_type", ['run', 'adhoc'])
    def test_remote_job_by_sockets(self, tmp_path, project_fixtures, job_type):
        """This test case is intended to be close to how the AWX use case works
        the process interacts with receptorctl with sockets
        sockets are used here, but worker is manually called instead of invoked by receptor
        """
        transmit_dir = project_fixtures / 'debug'
        worker_dir = tmp_path / 'for_worker'
        worker_dir.mkdir()

        process_dir = tmp_path / 'for_process'
        process_dir.mkdir()

        job_kwargs = self.get_job_kwargs(job_type)

        def transmit_method(transmit_sockfile_write):
            return ansible_runner.interface.run(
                streamer='transmit',
                _output=transmit_sockfile_write,
                private_data_dir=transmit_dir, **job_kwargs)

        def worker_method(transmit_sockfile_read, results_sockfile_write):
            return ansible_runner.interface.run(
                streamer='worker',
                _input=transmit_sockfile_read, _output=results_sockfile_write,
                private_data_dir=worker_dir, **job_kwargs)

        def process_method(results_sockfile_read):
            return ansible_runner.interface.run(
                streamer='process', quiet=True,
                _input=results_sockfile_read,
                private_data_dir=process_dir, status_handler=self.status_handler, **job_kwargs)

        transmit_socket_write, transmit_socket_read = socket.socketpair()
        results_socket_write, results_socket_read = socket.socketpair()

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            transmit_future = executor.submit(transmit_method, transmit_socket_write.makefile('wb'))
            # In real AWX implementation, worker is done via receptorctl
            executor.submit(worker_method, transmit_socket_read.makefile('rb'), results_socket_write.makefile('wb'))

            while True:
                if transmit_future.done():
                    break
                time.sleep(0.05)  # additionally, AWX calls cancel_callback()

            res = transmit_future.result()
            assert res.rc in (None, 0)
            assert res.status == 'unstarted'

            process_future = executor.submit(process_method, results_socket_read.makefile('rb'))

            while True:
                if process_future.done():
                    break
                time.sleep(0.05)  # additionally, AWX calls cancel_callback()

        for s in (transmit_socket_write, transmit_socket_read, results_socket_write, results_socket_read):
            s.close()

        assert self.status_data is not None
        if 'result_traceback' in self.status_data:
            raise Exception(self.status_data['result_traceback'])
        assert self.status_data.get('status') == 'successful'

        assert set(os.listdir(worker_dir)) == {'artifacts', 'inventory', 'project', 'env'}

        self.check_artifacts(str(process_dir), job_type)

    def test_process_isolation_executable_not_exist(self, tmp_path, mocker):
        """Case transmit should not fail if process isolation executable does not exist and
        worker should fail if process isolation executable does not exist
        """
        mocker.patch.object(ansible_runner.interface, 'check_isolation_executable_installed', return_value=False)

        job_kwargs = self.get_job_kwargs('run')
        job_kwargs['process_isolation'] = True
        job_kwargs['process_isolation_executable'] = 'does_not_exist'

        outgoing_buffer_file = tmp_path / 'buffer_out'
        outgoing_buffer_file.touch()
        outgoing_buffer = outgoing_buffer_file.open('b+r')

        transmitter = ansible_runner.interface.run(
            streamer='transmit',
            _output=outgoing_buffer,
            **job_kwargs,
        )

        # valide process_isolation kwargs are passed to transmitter
        assert transmitter.kwargs['process_isolation'] == job_kwargs['process_isolation']
        assert transmitter.kwargs['process_isolation_executable'] == job_kwargs['process_isolation_executable']

        # validate that transmit did not fail due to missing process isolation executable
        assert transmitter.rc in (None, 0)

        # validate that transmit buffer is not empty
        outgoing_buffer.seek(0)
        sent = outgoing_buffer.read()
        assert sent  # should not be blank at least

        # validate buffer contains kwargs
        assert b'kwargs' in sent

        # validate kwargs in buffer contain correct process_isolation and process_isolation_executable
        for line in sent.decode('utf-8').split('\n'):
            if "kwargs" in line:
                kwargs = json.loads(line).get("kwargs", {})
                assert kwargs['process_isolation'] == job_kwargs['process_isolation']
                assert kwargs['process_isolation_executable'] == job_kwargs['process_isolation_executable']
                break

        worker_dir = tmp_path / 'for_worker'
        incoming_buffer_file = tmp_path / 'buffer_in'
        incoming_buffer_file.touch()
        incoming_buffer = incoming_buffer_file.open('b+r')

        outgoing_buffer.seek(0)

        # validate that worker fails raise sys.exit(1) when process isolation executable does not exist
        with pytest.raises(SystemExit) as exc:
            ansible_runner.interface.run(
                streamer='worker',
                _input=outgoing_buffer,
                _output=incoming_buffer,
                private_data_dir=worker_dir,
            )
            assert exc.value.code == 1


@pytest.fixture
def transmit_stream(project_fixtures, tmp_path):
    outgoing_buffer = tmp_path / 'buffer'
    outgoing_buffer.touch()

    transmit_dir = project_fixtures / 'debug'
    with outgoing_buffer.open('wb') as f:
        transmitter = Transmitter(_output=f, private_data_dir=transmit_dir, playbook='debug.yml')
        status, rc = transmitter.run()

    assert rc in (None, 0)
    assert status == 'unstarted'
    return outgoing_buffer


@pytest.fixture
def worker_stream(transmit_stream, tmp_path):
    ingoing_buffer = tmp_path / 'buffer2'  # basically how some demos work
    ingoing_buffer.touch()

    worker_dir = tmp_path / 'worker_dir'
    worker_dir.mkdir()
    with transmit_stream.open('rb') as out:
        with ingoing_buffer.open('wb') as f:
            worker = Worker(_input=out, _output=f, private_data_dir=worker_dir)
            status, rc = worker.run()

            assert rc in (None, 0)
            assert status == 'successful'
            return ingoing_buffer


def test_worker_without_delete_no_dir(tmp_path, cli, transmit_stream):
    worker_dir = tmp_path / 'for_worker'

    with open(transmit_stream, 'rb') as stream:
        worker_args = ['worker', '--private-data-dir', str(worker_dir)]
        r = cli(worker_args, stdin=stream)

    assert '{"eof": true}' in r.stdout
    assert worker_dir.joinpath('project', 'debug.yml').exists()


def test_worker_without_delete_dir_exists(tmp_path, cli, transmit_stream):
    worker_dir = tmp_path / 'for_worker'
    worker_dir.mkdir()

    test_file_path = worker_dir / 'test_file.txt'
    test_file_path.write_text('data\n')

    with open(transmit_stream, 'rb') as stream:
        worker_args = ['worker', '--private-data-dir', str(worker_dir)]
        r = cli(worker_args, stdin=stream)

    assert '{"eof": true}' in r.stdout
    assert worker_dir.joinpath('project', 'debug.yml').exists()
    assert test_file_path.exists()


def test_worker_delete_no_dir(tmp_path, cli, transmit_stream):
    """
    Case where non-existing --delete is provided to worker command
    it should always delete everything both before and after the run
    """
    worker_dir = tmp_path / 'for_worker'

    with open(transmit_stream, 'rb') as f:
        worker_args = ['worker', '--private-data-dir', str(worker_dir), '--delete']
        r = cli(worker_args, stdin=f)

    assert '{"eof": true}' in r.stdout
    assert not worker_dir.exists()
    assert not worker_dir.joinpath('project', 'debug.yml').exists()


def test_worker_delete_dir_exists(tmp_path, cli, transmit_stream):
    """
    Case where non-existing --delete is provided to worker command
    it should always delete everything both before and after the run
    """
    worker_dir = tmp_path / 'for_worker'
    worker_dir.mkdir()

    test_file = worker_dir / 'test_file.txt'
    test_file.write_text('data\n')

    with open(transmit_stream, 'rb') as f:
        worker_args = ['worker', '--private-data-dir', str(worker_dir), '--delete']
        r = cli(worker_args, stdin=f)

    assert '{"eof": true}' in r.stdout
    assert not worker_dir.exists()
    assert not worker_dir.joinpath('project', 'debug.yml').exists()


def test_process_with_custom_ident(tmp_path, cli, worker_stream):
    process_dir = tmp_path / 'for_process'
    process_dir.mkdir()

    with open(worker_stream, 'rb') as f:
        process_args = ['process', str(process_dir), '--ident', 'custom_ident']
        r = cli(process_args, stdin=f)

    assert 'Hello world!' in r.stdout
    assert (process_dir / 'artifacts').exists()
    assert (process_dir / 'artifacts' / 'custom_ident').exists()
    assert (process_dir / 'artifacts' / 'custom_ident' / 'job_events').exists()


def test_missing_private_dir_transmit(tmpdir):
    outgoing_buffer = io.BytesIO()

    # Transmit
    with pytest.raises(ValueError) as excinfo:
        run(
            streamer='transmit',
            _output=outgoing_buffer,
            private_data_dir='/foo/bar/baz',
            playbook='debug.yml',
        )

    assert "private_data_dir path is either invalid or does not exist" in str(excinfo.value)


def test_garbage_private_dir_worker(tmp_path):
    worker_dir = tmp_path / 'for_worker'
    worker_dir.mkdir()
    incoming_buffer = io.BytesIO(
        b'{"kwargs": {"playbook": "debug.yml"}}\n{"zipfile": 5}\n\x01\x02\x03\x04\x05{"eof": true}\n')
    outgoing_buffer = io.BytesIO()

    # Worker
    run(
        streamer='worker',
        _input=incoming_buffer,
        _output=outgoing_buffer,
        private_data_dir=worker_dir,
    )
    outgoing_buffer.seek(0)
    sent = outgoing_buffer.readline()
    data = json.loads(sent)
    assert data['status'] == 'error'
    assert data['job_explanation'] == 'Failed to extract private data directory on worker.'
    assert data['result_traceback']


def test_unparsable_line_worker(tmp_path):
    worker_dir = tmp_path / 'for_worker'
    worker_dir.mkdir()
    incoming_buffer = io.BytesIO(b'')
    outgoing_buffer = io.BytesIO()

    # Worker
    run(
        streamer='worker',
        _input=incoming_buffer,
        _output=outgoing_buffer,
        private_data_dir=worker_dir,
    )
    outgoing_buffer.seek(0)
    sent = outgoing_buffer.readline()
    data = json.loads(sent)
    assert data['status'] == 'error'
    assert data['job_explanation'] == 'Failed to JSON parse a line from transmit stream.'


def test_unparsable_really_big_line_processor(tmp_path):
    process_dir = tmp_path / 'for_process'
    process_dir.mkdir()
    incoming_buffer = io.BytesIO(bytes(f'not-json-data with extra garbage:{"f"*10000}', encoding='utf-8'))

    def status_receiver(status_data, runner_config):
        assert status_data['status'] == 'error'
        assert 'Failed to JSON parse a line from worker stream.' in status_data['job_explanation']
        assert 'not-json-data with extra garbage:ffffffffff' in status_data['job_explanation']
        assert len(status_data['job_explanation']) < 2000

    run(
        streamer='process',
        _input=incoming_buffer,
        private_data_dir=process_dir,
        status_handler=status_receiver
    )
