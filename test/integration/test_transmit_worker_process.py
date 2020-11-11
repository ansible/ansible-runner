import io
import os

import pytest

from ansible_runner import run
from ansible_runner.streaming import Transmitter, Worker, Processor


def test_remote_job_interface(tmpdir, test_data_dir):
    worker_dir = str(tmpdir.mkdir('for_worker'))
    process_dir = str(tmpdir.mkdir('for_process'))

    original_dir = os.path.join(test_data_dir, 'debug')

    outgoing_buffer = io.BytesIO()

    # Intended AWX and Tower use case
    transmitter = Transmitter(
        _output=outgoing_buffer,
        private_data_dir=original_dir,
        playbook='debug.yml'
    )

    print(transmitter.kwargs)
    assert transmitter.kwargs.get('playbook', '') == 'debug.yml'

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
