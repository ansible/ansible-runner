import io
import os

import pytest
import json

from ansible_runner import run
from ansible_runner.streaming import Transmitter, Worker, Processor


@pytest.mark.parametrize("job_type", ['run', 'adhoc'])
def test_remote_job_interface(tmpdir, test_data_dir, job_type):
    worker_dir = str(tmpdir.mkdir('for_worker'))
    process_dir = str(tmpdir.mkdir('for_process'))

    original_dir = os.path.join(test_data_dir, 'debug')

    outgoing_buffer = io.BytesIO()

    # Intended AWX and Tower use case
    if job_type == 'run':
        job_kwargs = dict(playbook='debug.yml')
    else:
        job_kwargs = dict(
            module='setup',
            host_pattern='localhost'
        )
    transmitter = Transmitter(
        _output=outgoing_buffer,
        private_data_dir=original_dir,
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

    assert set(os.listdir(worker_dir)) == {'artifacts', 'inventory', 'project'}, outgoing_buffer.getvalue()

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
