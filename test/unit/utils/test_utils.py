# pylint: disable=W0212

import base64
import datetime
import io
import json
import os
import signal
import time
import stat
import zipfile

from pathlib import Path

import pytest

from ansible_runner.utils import (
    isplaybook,
    isinventory,
    check_isolation_executable_installed,
    args2cmdline,
    sanitize_container_name,
    signal_handler,
)
from ansible_runner.utils.base64io import _to_bytes, Base64IO
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


def test_check_isolation_executable_installed():
    assert check_isolation_executable_installed("true")
    assert not check_isolation_executable_installed("does-not-exist")


@pytest.mark.parametrize('container_name,expected_name', [
    ('foo?bar', 'foo_bar'),
    ('096aac5c-024d-453e-9725-779dc8b3faee', '096aac5c-024d-453e-9725-779dc8b3faee'),  # uuid4
    (42, '42')  # AWX will use primary keys and may not be careful about type
])
def test_sanitize_container_name(container_name, expected_name):
    assert sanitize_container_name(str(container_name)) == expected_name


@pytest.mark.parametrize('symlink_dest,check_content', [
    ('ordinary_file.txt', ['my_link']),
    ('ordinary_directory', ['my_link/dir_file.txt']),
    ('.', ['my_link/ordinary_directory/dir_file.txt', 'my_link/my_link/ordinary_file.txt']),
    ('filedoesnotexist.txt', [])
], ids=['local', 'directory', 'recursive', 'bad'])
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
    for _ in range(2):

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


def test_transmit_symlink_to_external_path_is_rejected(tmp_path):
    """Symbolic links whose target falls OUTSIDE the destination directory
    must be refused, not faithfully recreated. Round-tripping an absolute /
    out-of-tree symlink is what enables the symlink-tar-slip primitive.
    """
    pdd = tmp_path / "src"
    pdd.mkdir()
    (pdd / "ordinary_file.txt").write_text("hello")
    (pdd / "my_link").symlink_to("/bin")
    buf = io.BytesIO()
    buf.name = "not_stdout"
    stream_dir(str(pdd), buf)
    dest = tmp_path / "dest"
    dest.mkdir()
    buf.seek(0)
    header = json.loads(buf.readline().strip())
    with pytest.raises(zipfile.BadZipFile, match="escape"):
        unstream_dir(buf, header["zipfile"], str(dest))
    assert not (dest / "my_link").exists()


def _build_symlink_escape_zip(out_path, escape_dir):
    """Build a zip with a symlink entry that escapes outside escape_dir plus a
    regular-file entry that traverses through that symlink.
    """
    s_iflnk_flag = 0xA000
    external = (0o777 | s_iflnk_flag) << 16
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        link_info = zipfile.ZipInfo("evil-link")
        link_info.create_system = 3
        link_info.external_attr = external
        zf.writestr(link_info, str(escape_dir).encode())
        file_info = zipfile.ZipInfo("evil-link/PWNED.txt")
        file_info.create_system = 3
        file_info.external_attr = (0o644 | 0x8000) << 16
        zf.writestr(file_info, b"SENTINEL")


def test_unstream_dir_rejects_symlink_target_escape(tmp_path):
    """Refuse to extract a zip whose symlink entry targets a directory outside
    the destination, even when the next file entry traverses through it.
    """
    extract_dir = tmp_path / "private_data_dir"
    extract_dir.mkdir()
    escape_dir = tmp_path / "outside"
    escape_dir.mkdir()
    zip_path = tmp_path / "malicious.zip"
    _build_symlink_escape_zip(str(zip_path), str(escape_dir))
    # Wrap the raw zip in the json+base64 framing unstream_dir reads.
    body = zip_path.read_bytes()
    encoded = base64.b64encode(body)
    stream = io.BytesIO(
        json.dumps({"zipfile": len(body)}).encode() + b"\n" + encoded
    )
    first_line = stream.readline()
    assert b"zipfile" in first_line
    with pytest.raises(zipfile.BadZipFile, match="escape"):
        unstream_dir(stream, len(body), str(extract_dir))
    # The sentinel file MUST NOT exist in the escape directory; the planted
    # link MUST NOT survive in the extraction directory.
    assert not (escape_dir / "PWNED.txt").exists()
    assert not (extract_dir / "evil-link").exists()


def _stream_of(zip_path):
    """Wrap a raw zip file in the json+base64 framing unstream_dir reads."""
    body = zip_path.read_bytes()
    stream = io.BytesIO(
        json.dumps({"zipfile": len(body)}).encode() + b"\n" + base64.b64encode(body)
    )
    stream.readline()
    return stream, len(body)


def test_unstream_dir_noncanonical_member_name_stays_contained(tmp_path):
    """A member name containing ".." must not reach a symlink planted beside it.

    ``ZipFile.extract()`` sanitizes member names by *dropping* ``..`` components
    rather than resolving them, so it writes ``a/../link/f`` to ``a/link/f``
    while ``normpath()`` of the same name says ``link/f``. Because the member is
    written to the path we validated rather than to one predicted for
    ``extract()``, the planted link is never traversed.
    """
    dest = tmp_path / "dest"
    (dest / "a").mkdir(parents=True)
    escape_dir = tmp_path / "outside"
    escape_dir.mkdir()
    # An attacker-planted (or simply pre-existing) link in the destination.
    (dest / "a" / "link").symlink_to(escape_dir)

    zip_path = tmp_path / "noncanonical.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo("a/../link/PWNED.txt")
        info.create_system = 3
        info.external_attr = (0o644 | 0x8000) << 16
        zf.writestr(info, b"SENTINEL")

    stream, size = _stream_of(zip_path)
    # The planted link was already in the destination, so the transfer is
    # refused outright -- but only after the member has been written, which is
    # what lets us assert where it went.
    with pytest.raises(zipfile.BadZipFile, match="escape"):
        unstream_dir(stream, size, str(dest))
    assert not (escape_dir / "PWNED.txt").exists()
    assert (dest / "link" / "PWNED.txt").read_bytes() == b"SENTINEL"


def test_unstream_dir_does_not_write_through_existing_symlink(tmp_path):
    """A regular member must not be written through a symlink already present at
    its destination path, e.g. in a reused private_data_dir.
    """
    dest = tmp_path / "dest"
    dest.mkdir()
    escape_dir = tmp_path / "outside"
    escape_dir.mkdir()
    victim = escape_dir / "victim.txt"
    victim.write_text("original")
    (dest / "victim.txt").symlink_to(victim)

    zip_path = tmp_path / "through-link.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo("victim.txt")
        info.create_system = 3
        info.external_attr = (0o644 | 0x8000) << 16
        zf.writestr(info, b"SENTINEL")

    stream, size = _stream_of(zip_path)
    unstream_dir(stream, size, str(dest))
    assert victim.read_text() == "original"
    assert (dest / "victim.txt").read_bytes() == b"SENTINEL"
    assert not (dest / "victim.txt").is_symlink()


def test_unstream_dir_preserves_safe_symlinks(tmp_path):
    """Round-trip a tree that contains a SAFE symlink (target inside the
    destination) and assert the symlink survives.
    """
    pdd = tmp_path / "src"
    pdd.mkdir()
    (pdd / "real.txt").write_text("payload")
    (pdd / "alias").symlink_to("real.txt")
    buf = io.BytesIO()
    buf.name = "not_stdout"
    stream_dir(str(pdd), buf)
    dest = tmp_path / "dest"
    dest.mkdir()
    buf.seek(0)
    header = json.loads(buf.readline().strip())
    unstream_dir(buf, header["zipfile"], str(dest))
    assert (dest / "alias").is_symlink()
    assert os.readlink(dest / "alias") == "real.txt"
    assert (dest / "real.txt").read_text() == "payload"


def _transmit(source_dir):
    """Stream a directory and return a buffer positioned past the header, plus
    the encoded size, ready to hand to unstream_dir.
    """
    buf = io.BytesIO()
    buf.name = "not_stdout"
    stream_dir(str(source_dir), buf)
    buf.seek(0)
    header = json.loads(buf.readline().strip())
    return buf, header["zipfile"]


def _symlink_only_zip(out_path, links):
    """Build a zip of nothing but symlink members, in the given order."""
    external = (0o777 | 0xA000) << 16
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, target in links:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = external
            zf.writestr(info, target.encode())


def test_transmit_symlink_escaping_only_after_a_later_link_is_rejected(tmp_path):
    """A link that escapes only once a LATER member exists must be refused.

    ``artifacts -> project/../other_job`` resolves inside the destination while
    ``project`` is absent, because realpath() collapses ``project/..``
    lexically over a component that does not exist, and outside it as soon as
    ``project -> .`` is created. os.walk() reports the broken link among files
    and the directory link among dirs, so stream_dir always emits ``artifacts``
    first and the escape is only visible once the whole archive is on disk.
    """
    pdd = tmp_path / "src"
    pdd.mkdir()
    (pdd / "ordinary_file.txt").write_text("hello")
    (pdd / "artifacts").symlink_to("project/../other_job")
    (pdd / "project").symlink_to(".")

    dest = tmp_path / "dest"
    dest.mkdir()
    buf, size = _transmit(pdd)
    with pytest.raises(zipfile.BadZipFile, match="escape"):
        unstream_dir(buf, size, str(dest))

    # Neither half of the pair may survive: writing to "<dest>/artifacts/<id>",
    # as the artifact dir setup does, would otherwise land in tmp_path.
    assert not os.path.lexists(dest / "artifacts")
    assert not os.path.lexists(dest / "project")
    assert not (tmp_path / "other_job").exists()


def test_unstream_dir_rejects_symlink_redirected_by_later_member(tmp_path):
    """The same escape, without relying on os.walk to order the two links."""
    dest = tmp_path / "private_data_dir"
    dest.mkdir()
    zip_path = tmp_path / "deferred.zip"
    _symlink_only_zip(zip_path, [("artifacts", "project/../other_job"), ("project", ".")])

    stream, size = _stream_of(zip_path)
    with pytest.raises(zipfile.BadZipFile, match="escape"):
        unstream_dir(stream, size, str(dest))
    assert not os.path.lexists(dest / "artifacts")
    assert not os.path.lexists(dest / "project")


def test_unstream_dir_rejects_symlink_pair_across_two_archives(tmp_path):
    """Two archives unpacked into the same destination must not compose into an
    escape. Neither link escapes on its own, so the second transfer is only
    refusable by checking links an earlier transfer left behind.
    """
    dest = tmp_path / "private_data_dir"
    dest.mkdir()

    first = tmp_path / "first.zip"
    _symlink_only_zip(first, [("artifacts", "project/../other_job")])
    stream, size = _stream_of(first)
    unstream_dir(stream, size, str(dest))
    assert os.path.lexists(dest / "artifacts")

    second = tmp_path / "second.zip"
    _symlink_only_zip(second, [("project", ".")])
    stream, size = _stream_of(second)
    with pytest.raises(zipfile.BadZipFile, match="escape"):
        unstream_dir(stream, size, str(dest))


def test_unstream_dir_preserves_symlink_resolved_through_a_later_link(tmp_path):
    """Deferred resolution is not itself suspicious: a link whose target only
    resolves through a link created after it is kept, as long as the result
    lands inside the destination.
    """
    pdd = tmp_path / "src"
    pdd.mkdir()
    (pdd / "real.txt").write_text("payload")
    (pdd / "here").symlink_to(".")
    (pdd / "alias").symlink_to("here/real.txt")

    dest = tmp_path / "dest"
    dest.mkdir()
    buf, size = _transmit(pdd)
    unstream_dir(buf, size, str(dest))
    assert os.readlink(dest / "alias") == "here/real.txt"
    assert (dest / "alias").read_text() == "payload"


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


class TestBase64IO:
    def test_init_fails(self):
        with pytest.raises(TypeError, match='Base64IO wrapped object must have attributes'):
            Base64IO(None)

    def test__passthrough_interactive_check_bad_method(self):
        obj = Base64IO(io.StringIO('test'))
        assert not obj._passthrough_interactive_check('invalid_method')

    def test_write(self, tmp_path):
        tmpfile = tmp_path / "TestBase64IO_test_write.txt"
        tmpfile.touch()
        with tmpfile.open(mode='br') as t:
            obj = Base64IO(t)
            with pytest.raises(IOError, match='Stream is not writable'):
                obj.write(b'')
            obj.close()
            with pytest.raises(ValueError, match='I/O operation on closed file.'):
                obj.write(b'')

    def test__read_additional_data_removing_whitespace(self):
        obj = Base64IO(io.StringIO(''))
        data = _to_bytes('te s t')
        assert obj._read_additional_data_removing_whitespace(data, 4) == b'test'
