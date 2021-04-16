import io
import os
import socket
import concurrent.futures
import time
import tempfile

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

    def check_artifacts(self, process_dir, job_type):

        assert set(os.listdir(process_dir)) == {'artifacts',}

        events_dir = os.path.join(process_dir, 'artifacts', 'job_events')
        events = []
        for file in os.listdir(events_dir):
            with open(os.path.join(events_dir, file), 'r') as f:
                if file in ('status', 'rc'):
                    continue
                content = f.read()
                events.append(json.loads(content))
        stdout = '\n'.join(event['stdout'] for event in events)

        if job_type == 'run':
            assert 'Hello world!' in stdout
        else:
            assert '"ansible_facts"' in stdout

    @pytest.mark.parametrize("job_type", ['run', 'adhoc'])
    def test_remote_job_interface(self, tmpdir, test_data_dir, job_type):
        transmit_dir = os.path.join(test_data_dir, 'debug')
        worker_dir = str(tmpdir.mkdir('for_worker'))
        process_dir = str(tmpdir.mkdir('for_process'))
        job_kwargs = self.get_job_kwargs(job_type)

        outgoing_buffer = tempfile.NamedTemporaryFile()

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

        incoming_buffer = tempfile.NamedTemporaryFile()

        outgoing_buffer.seek(0)

        worker = Worker(_input=outgoing_buffer, _output=incoming_buffer, private_data_dir=worker_dir)
        worker.run()

        outgoing_buffer.seek(0)
        assert set(os.listdir(worker_dir)) == {'artifacts', 'inventory', 'project', 'env'}, outgoing_buffer.read()

        incoming_buffer.seek(0)  # again, be kind, rewind

        processor = Processor(_input=incoming_buffer, private_data_dir=process_dir)
        processor.run()

        self.check_artifacts(process_dir, job_type)


    @pytest.mark.parametrize("job_type", ['run', 'adhoc'])
    def test_remote_job_by_sockets(self, tmpdir, test_data_dir, container_runtime_installed, job_type):
        """This test case is intended to be close to how the AWX use case works
        the process interacts with receptorctl with sockets
        sockets are used here, but worker is manually called instead of invoked by receptor
        """
        transmit_dir = os.path.join(test_data_dir, 'debug')
        worker_dir = str(tmpdir.mkdir('for_worker'))
        process_dir = str(tmpdir.mkdir('for_process'))
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

        self.check_artifacts(process_dir, job_type)


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


def test_garbage_private_dir_worker(tmpdir):
    worker_dir = str(tmpdir.mkdir('for_worker'))
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
    sent = outgoing_buffer.getvalue()
    assert b'"status": "error"' in sent


def test_unparsable_private_dir_worker(tmpdir):
    worker_dir = str(tmpdir.mkdir('for_worker'))
    incoming_buffer = io.BytesIO(b'')
    outgoing_buffer = io.BytesIO()

    # Worker
    run(
        streamer='worker',
        _input=incoming_buffer,
        _output=outgoing_buffer,
        private_data_dir=worker_dir,
    )
    sent = outgoing_buffer.getvalue()
    assert b'"status": "error"' in sent


def test_unparsable_private_dir_processor(tmpdir):
    process_dir = str(tmpdir.mkdir('for_process'))
    incoming_buffer = io.BytesIO(b'')

    processor = run(
        streamer='process',
        _input=incoming_buffer,
        private_data_dir=process_dir,
    )
    assert processor.status == 'error'
