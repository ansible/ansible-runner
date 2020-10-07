import os
import io

from ansible_runner.streaming import Transmitter, Worker, Processor


def peek_contents(buffer):
    pos = buffer.tell()
    content = buffer.read()
    buffer.seek(pos)
    return content


def test_remote_job_interface(tmpdir, test_data_dir):
    worker_dir = str(tmpdir.mkdir('for_worker'))
    process_dir = str(tmpdir.mkdir('for_process'))

    original_dir = os.path.join(test_data_dir, 'debug')

    outgoing_buffer = io.BytesIO()

    # Intended AWX and Tower use case
    transmitter = Transmitter(
        _output = outgoing_buffer,
        private_data_dir = original_dir,
        playbook = 'debug.yml'
    )

    print(transmitter.kwargs)
    assert transmitter.kwargs.get('playbook', '') == 'debug.yml'

    status, rc = transmitter.run()
    assert rc in (None, 0)
    assert status == 'unstarted'

    outgoing_buffer.seek(0)  # rewind so we can start reading

    sent = peek_contents(outgoing_buffer)
    assert sent  # should not be blank at least
    assert b'zipfile' in sent

    incoming_buffer = io.BytesIO()

    worker = Worker(
        _input = outgoing_buffer,
        _output = incoming_buffer,
        private_data_dir = worker_dir
    )
    worker.run()

    assert set(os.listdir(worker_dir)) == set(['artifacts', 'inventory', 'project']), outgoing_buffer.getvalue()

    incoming_buffer.seek(0)  # again, be kind, rewind

    processor = Processor(
        _input = incoming_buffer,
        private_data_dir = process_dir
    )
    processor.run()

    assert os.listdir(process_dir) == ['project', 'artifacts'], outgoing_buffer.getvalue()
