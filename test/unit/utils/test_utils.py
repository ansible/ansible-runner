import datetime
import io
import json
import os
import signal
import time
import stat

from pathlib import Path

import pytest

from ansible_runner.utils import (
    isplaybook,
    isinventory,
    args2cmdline,
    sanitize_container_name,
    signal_handler,
)
from ansible_runner.utils.streaming import stream_dir, unstream_dir


@pytest.mark.parametrize('playbook', ('foo', {}, {'foo': 'bar'}, True, False, None))
def test_isplaybook_invalid(playbook):
    assert isplaybook(playbook) is False


@pytest.mark.parametrize('playbook', (['foo'], []))
def test_isplaybook(playbook):
    assert isplaybook(playbook) is True


@pytest.mark.parametrize('inventory', ('hosts,', {}, {'foo': 'bar'}))
def test_isinventory(inventory):
    assert isinventory(inventory) is True


@pytest.mark.parametrize('inventory', ([], ['foo'], True, False, None))
def test_isinventory_invalid(inventory):
    assert isinventory(inventory) is False


def test_args2cmdline():
    res = args2cmdline('ansible', '-m', 'setup', 'localhost')
    assert res == 'ansible -m setup localhost'


@pytest.mark.parametrize('container_name,expected_name', [
    ('foo?bar', 'foo_bar'),
    ('096aac5c-024d-453e-9725-779dc8b3faee', '096aac5c-024d-453e-9725-779dc8b3faee'),  # uuid4
    (42, '42')  # AWX will use primary keys and may not be careful about type
])
def test_sanitize_container_name(container_name, expected_name):
    sanitize_container_name(str(container_name)) == expected_name


@pytest.mark.parametrize('symlink_dest,check_content', [
    ('/bin', []),
    ('ordinary_file.txt', ['my_link']),
    ('ordinary_directory', ['my_link/dir_file.txt']),
    ('.', ['my_link/ordinary_directory/dir_file.txt', 'my_link/my_link/ordinary_file.txt']),
    ('filedoesnotexist.txt', [])
], ids=['global', 'local', 'directory', 'recursive', 'bad'])
def test_transmit_symlink(tmp_path, symlink_dest, check_content):
    symlink_dest = Path(symlink_dest)

    # prepare the input private_data_dir directory to zip
    pdd = tmp_path / 'symlink_zip_test'
    pdd.mkdir()

    # Create some basic shared demo content
    with open(pdd / 'ordinary_file.txt', 'w') as f:
        f.write('hello world')

    ord_dir = pdd / 'ordinary_directory'
    ord_dir.mkdir()
    with open(ord_dir / 'dir_file.txt', 'w') as f:
        f.write('hello world')

    old_symlink_path = pdd / 'my_link'
    old_symlink_path.symlink_to(symlink_dest)

    # SANITY - set expectations for the symlink
    assert old_symlink_path.is_symlink()
    assert os.readlink(old_symlink_path) == str(symlink_dest)

    # zip and stream the data into the in-memory buffer outgoing_buffer
    outgoing_buffer = io.BytesIO()
    outgoing_buffer.name = 'not_stdout'
    stream_dir(pdd, outgoing_buffer)

    # prepare the destination private_data_dir to transmit to
    dest_dir = tmp_path / 'symlink_zip_dest'
    dest_dir.mkdir()

    # Extract twice so we assure that existing data does not break things
    for i in range(2):

        # rewind the buffer and extract into destination private_data_dir
        outgoing_buffer.seek(0)
        first_line = outgoing_buffer.readline()
        size_data = json.loads(first_line.strip())
        unstream_dir(outgoing_buffer, size_data['zipfile'], dest_dir)

        # Assure the new symlink is still the same type of symlink
        new_symlink_path = dest_dir / 'my_link'
        assert new_symlink_path.is_symlink()
        assert os.readlink(new_symlink_path) == str(symlink_dest)

    for fname in check_content:
        abs_path = dest_dir / fname
        assert abs_path.exists(), f'Expected "{fname}" in target dir to be a file with content.'
        with open(abs_path, 'r') as f:
            assert f.read() == 'hello world'


@pytest.mark.timeout(timeout=3)
def test_stream_dir_no_hang_on_pipe(tmp_path):
    # prepare the input private_data_dir directory to zip
    pdd = tmp_path / 'timeout_test'
    pdd.mkdir()

    with open(pdd / 'ordinary_file.txt', 'w') as f:
        f.write('hello world')

    # make pipe, similar to open_fifo_write
    os.mkfifo(pdd / 'my_pipe', stat.S_IRUSR | stat.S_IWUSR)

    # zip and stream the data into the in-memory buffer outgoing_buffer
    outgoing_buffer = io.BytesIO()
    outgoing_buffer.name = 'not_stdout'
    stream_dir(pdd, outgoing_buffer)


@pytest.mark.timeout(timeout=3)
def test_unstream_dir_no_hang_on_pipe(tmp_path):
    # prepare the input private_data_dir directory to zip
    pdd = tmp_path / 'timeout_test_source_dir'
    pdd.mkdir()

    with open(pdd / 'ordinary_file.txt', 'w') as f:
        f.write('hello world')

    # zip and stream the data into the in-memory buffer outgoing_buffer
    outgoing_buffer = io.BytesIO()
    outgoing_buffer.name = 'not_stdout'
    stream_dir(pdd, outgoing_buffer)

    dest_dir = tmp_path / 'timeout_test_dest'
    dest_dir.mkdir()

    # We create the pipe in the same location as an archived file to trigger the bug
    os.mkfifo(dest_dir / 'ordinary_file.txt', stat.S_IRUSR | stat.S_IWUSR)

    outgoing_buffer.seek(0)
    first_line = outgoing_buffer.readline()
    size_data = json.loads(first_line.strip())
    unstream_dir(outgoing_buffer, size_data['zipfile'], dest_dir)


@pytest.mark.parametrize('fperm', [
    0o777,
    0o666,
    0o555,
    0o700,
])
def test_transmit_permissions(tmp_path, fperm):
    # breakpoint()
    pdd = tmp_path / 'transmit_permission_test'
    pdd.mkdir()

    old_file_path = pdd / 'ordinary_file.txt'
    with open(old_file_path, 'w') as f:
        f.write('hello world')
    old_file_path.chmod(fperm)

    # SANITY - set expectations for the file
    # assert oct(os.stat(old_file_path).st_mode & 0o777) == oct(fperm)
    assert oct(old_file_path.stat().st_mode & 0o777) == oct(fperm)

    outgoing_buffer = io.BytesIO()
    outgoing_buffer.name = 'not_stdout'
    stream_dir(pdd, outgoing_buffer)

    dest_dir = tmp_path / 'transmit_permission_dest'

    outgoing_buffer.seek(0)
    first_line = outgoing_buffer.readline()
    size_data = json.loads(first_line.strip())
    unstream_dir(outgoing_buffer, size_data['zipfile'], dest_dir)

    # Assure the new file is the same permissions
    new_file_path = dest_dir / 'ordinary_file.txt'
    assert oct(new_file_path.stat().st_mode) == oct(old_file_path.stat().st_mode)


def test_transmit_modtimes(tmp_path):
    source_dir = tmp_path / 'source'
    source_dir.mkdir()

    # python ZipFile uses an old standard that stores seconds in 2 second increments
    # https://stackoverflow.com/questions/64048499/zipfile-lib-weird-behaviour-with-seconds-in-modified-time
    (source_dir / 'b.txt').touch()
    time.sleep(2.0)  # flaky for anything less
    (source_dir / 'a.txt').touch()

    very_old_file = source_dir / 'very_old.txt'
    very_old_file.touch()
    old_datetime = os.path.getmtime(source_dir / 'a.txt') - datetime.timedelta(days=1).total_seconds()
    os.utime(very_old_file, (old_datetime, old_datetime))

    # sanity, verify assertions pass for source dir
    mod_delta = os.path.getmtime(source_dir / 'a.txt') - os.path.getmtime(source_dir / 'b.txt')
    assert mod_delta >= 1.0

    outgoing_buffer = io.BytesIO()
    outgoing_buffer.name = 'not_stdout'
    stream_dir(source_dir, outgoing_buffer)

    dest_dir = tmp_path / 'dest'
    dest_dir.mkdir()

    outgoing_buffer.seek(0)
    first_line = outgoing_buffer.readline()
    size_data = json.loads(first_line.strip())
    unstream_dir(outgoing_buffer, size_data['zipfile'], dest_dir)

    # Assure modification times are internally consistent
    mod_delta = os.path.getmtime(dest_dir / 'a.txt') - os.path.getmtime(dest_dir / 'b.txt')
    assert mod_delta >= 1.0

    # Assure modification times are same as original (to the rounded second)
    for filename in ('a.txt', 'b.txt', 'very_old.txt'):
        difference = abs(os.path.getmtime(dest_dir / filename) - os.path.getmtime(source_dir / filename))
        assert difference < 2.0

    # Assure the very old timestamp is preserved
    old_delta = os.path.getmtime(dest_dir / 'a.txt') - os.path.getmtime(source_dir / 'very_old.txt')
    assert old_delta >= datetime.timedelta(days=1).total_seconds() - 2.


def test_transmit_file_from_before_1980s(tmp_path):
    source_dir = tmp_path / 'source'
    source_dir.mkdir()

    old_file = source_dir / 'cassette_tape.txt'
    old_file.touch()

    old_timestamp = datetime.datetime(year=1978, month=7, day=28).timestamp()
    os.utime(old_file, (old_timestamp, old_timestamp))

    outgoing_buffer = io.BytesIO()
    outgoing_buffer.name = 'not_stdout'
    stream_dir(source_dir, outgoing_buffer)

    dest_dir = tmp_path / 'dest'
    dest_dir.mkdir()

    outgoing_buffer.seek(0)
    first_line = outgoing_buffer.readline()
    size_data = json.loads(first_line.strip())
    unstream_dir(outgoing_buffer, size_data['zipfile'], dest_dir)


def test_signal_handler(mocker):
    """Test the default handler is set to handle the correct signals"""

    class MockEvent:
        def __init__(self):
            self._is_set = False

        def set(self):
            self._is_set = True

        def is_set(self):
            return self._is_set

    mocker.patch('ansible_runner.utils.threading.main_thread', return_value='thread0')
    mocker.patch('ansible_runner.utils.threading.current_thread', return_value='thread0')
    mocker.patch('ansible_runner.utils.threading.Event', MockEvent)
    mock_signal = mocker.patch('ansible_runner.utils.signal.signal')

    assert signal_handler()() is False
    assert mock_signal.call_args_list[0][0][0] == signal.SIGTERM
    assert mock_signal.call_args_list[1][0][0] == signal.SIGINT


def test_signal_handler_outside_main_thread(mocker):
    """Test that the default handler will not try to set signal handlers if not in the main thread"""

    mocker.patch('ansible_runner.utils.threading.main_thread', return_value='thread0')
    mocker.patch('ansible_runner.utils.threading.current_thread', return_value='thread1')

    assert signal_handler() is None


def test_signal_handler_set(mocker):
    """Test that the default handler calls the set() method"""

    class MockEvent:
        def __init__(self):
            self._is_set = False

        def set(self):
            raise AttributeError('Raised intentionally')

        def is_set(self):
            return self._is_set

    mocker.patch('ansible_runner.utils.threading.main_thread', return_value='thread0')
    mocker.patch('ansible_runner.utils.threading.current_thread', return_value='thread0')
    mocker.patch('ansible_runner.utils.threading.Event', MockEvent)
    mock_signal = mocker.patch('ansible_runner.utils.signal.signal')

    signal_handler()

    with pytest.raises(AttributeError, match='Raised intentionally'):
        mock_signal.call_args[0][1]('number', 'frame')
