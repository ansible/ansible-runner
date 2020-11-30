import io
import os
import socket
import concurrent
import time
import traceback

import pytest
import json

from ansible_runner import run
from ansible_runner.streaming import Transmitter, Worker, Processor

import ansible_runner.interface  # AWX import pattern


@pytest.mark.parametrize("job_type", ['run', 'adhoc'])
def test_remote_job_interface(tmpdir, test_data_dir, job_type):
    transmit_dir = os.path.join(test_data_dir, 'debug')
    worker_dir = str(tmpdir.mkdir('for_worker'))
    process_dir = str(tmpdir.mkdir('for_process'))

    outgoing_buffer = io.BytesIO()

    # Intended AWX and Tower use case
    if job_type == 'run':
        job_kwargs = dict(playbook='debug.yml')
    else:
        job_kwargs = dict(module='setup', host_pattern='localhost')
    # also test use of user env vars
    job_kwargs['envvars'] = dict(MY_ENV_VAR='bogus')

    transmitter = Transmitter(
        _output=outgoing_buffer,
        private_data_dir=transmit_dir,
        **job_kwargs
    )

    for key, value in job_kwargs.items():
        assert transmitter.kwargs.get(key, '') == value

    status, rc = transmitter.run()
    assert rc in (None, 0)
    assert status == 'unstarted'

    outgoing_buffer.seek(0)  # rewind so we can start reading

    sent = outgoing_buffer.getvalue()
    assert sent  # should not be blank at least
    assert b'zipfile' in sent

    incoming_buffer = io.BytesIO()

    worker = Worker(
        _input=outgoing_buffer,
        _output=incoming_buffer,
        private_data_dir=worker_dir
    )
    worker.run()

    assert set(os.listdir(worker_dir)) == {'artifacts', 'inventory', 'project', 'env'}, outgoing_buffer.getvalue()

    incoming_buffer.seek(0)  # again, be kind, rewind

    processor = Processor(
        _input=incoming_buffer,
        private_data_dir=process_dir
    )
    processor.run()

    assert set(os.listdir(process_dir)) == {'artifacts',}, outgoing_buffer.getvalue()

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
def test_remote_job_by_sockets(tmpdir, test_data_dir, job_type):
    """This test case is intended to be close to how the AWX use case works
    the process interacts with receptorctl with sockets
    sockets are used here, but worker is manually called instead of invoked by receptor
    """
    transmit_dir = os.path.join(test_data_dir, 'debug')
    worker_dir = str(tmpdir.mkdir('for_worker'))
    process_dir = str(tmpdir.mkdir('for_process'))

    # Intended AWX and Tower use case
    if job_type == 'run':
        job_kwargs = dict(playbook='debug.yml')
    else:
        job_kwargs = dict(module='setup', host_pattern='localhost')
    # also test use of user env vars
    job_kwargs['envvars'] = dict(MY_ENV_VAR='bogus')


    def transmit_method(transmit_sockfile_write):
        ansible_runner.interface.run(
            streamer='transmit',
            _output=transmit_sockfile_write,
            private_data_dir=transmit_dir,
            **job_kwargs
        )


    def worker_method(transmit_sockfile_read, results_sockfile_write):
        # ThreadPoolExecutor does not handle tracebacks nicely
        try:
            ansible_runner.interface.run(
                streamer='worker',
                _input=transmit_sockfile_read,
                _output=results_sockfile_write,
                private_data_dir=worker_dir,
                **job_kwargs
            )
        except Exception:
            traceback.print_exc()
            raise


    def process_method(results_sockfile_read):
        ansible_runner.interface.run(
            streamer='process',
            quiet=True,
            _input=results_sockfile_read,
            private_data_dir=process_dir,
            **job_kwargs
        )

    transmit_socket_write, transmit_socket_read = socket.socketpair()
    results_socket_write, results_socket_read = socket.socketpair()

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        transmit_future = executor.submit(transmit_method, transmit_socket_write.makefile('wb'))
        # we will not make assertions on, or manage, worker directly
        worker_future = executor.submit(worker_method, transmit_socket_read.makefile('rb'), results_socket_write.makefile('wb'))

        while True:
            # In AWX this loop is where the cancel callback is checked, but here we just check transmit
            transmit_finished = transmit_future.done()
            if transmit_finished:
                break
            time.sleep(0.05)

        process_future = executor.submit(process_method, results_socket_read.makefile('rb'))

        while True:
            worker_finished = worker_future.done()
            if worker_finished:
                break
            time.sleep(0.05)

        while True:
            # this is the second cancel loop, which is still pretty similar to the first
            process_finished = process_future.done()
            if process_finished:
                # process_result = process_future.result()
                break
            time.sleep(0.05)


    # close all the sockets
    transmit_socket_write.close()
    transmit_socket_read.close()
    results_socket_write.close()
    results_socket_read.close()

    assert set(os.listdir(worker_dir)) == {'artifacts', 'inventory', 'project', 'env'}

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
    assert b'"status": "failed"' in sent


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
