import os
import stat
import subprocess
import sys
import textwrap

import pytest

from ansible_runner.utils._daemonize import (
    AlreadyRunningError,
    DaemonContext,
    PIDFILE_MODE,
    _reclaim_stale_pidfile,
    pid_is_running,
    read_pidfile,
    remove_pidfile,
    write_pidfile,
)


def make_dead_pid():
    """Return a PID that is guaranteed to be gone, and reaped so it is not a zombie."""
    proc = subprocess.Popen([sys.executable, '-c', ''])  # pylint: disable=R1732
    proc.wait()
    return proc.pid


def test_read_pidfile_missing(tmp_path):
    assert read_pidfile(str(tmp_path / 'nope')) is None


@pytest.mark.parametrize('contents,expected', (
    ('', None),
    ('\n', None),
    ('not-a-pid', None),
    ('1234', 1234),
    ('1234\n', 1234),
    (' 1234 \n', 1234),
    ('1234\nnoise\n', 1234),
))
def test_read_pidfile(tmp_path, contents, expected):
    pidfile = tmp_path / 'pid'
    pidfile.write_text(contents)
    assert read_pidfile(str(pidfile)) == expected


def test_read_pidfile_directory(tmp_path):
    assert read_pidfile(str(tmp_path)) is None


def test_pid_is_running_self():
    assert pid_is_running(os.getpid()) is True


def test_pid_is_running_dead():
    assert pid_is_running(make_dead_pid()) is False


@pytest.mark.parametrize('pid', (0, -1))
def test_pid_is_running_non_positive(pid, mocker):
    # A non-positive PID must never reach os.kill(): 0 would signal our own process
    # group and -1 would signal every process we are allowed to signal.
    kill = mocker.patch('ansible_runner.utils._daemonize.os.kill')
    assert pid_is_running(pid) is False
    kill.assert_not_called()


def test_pid_is_running_permission_denied(mocker):
    mocker.patch('ansible_runner.utils._daemonize.os.kill', side_effect=PermissionError)
    assert pid_is_running(999999) is True


def test_write_pidfile_creates_file(tmp_path):
    pidfile = tmp_path / 'pid'

    # The PID file mode is subject to the umask, which is now inherited rather than
    # reset to 0, so pin it for the duration of the assertion.
    umask = os.umask(0o022)
    try:
        write_pidfile(str(pidfile))
    finally:
        os.umask(umask)

    assert pidfile.read_text() == f"{os.getpid()}\n"
    assert stat.S_IMODE(pidfile.stat().st_mode) == PIDFILE_MODE


def test_write_pidfile_live_owner_raises(tmp_path):
    pidfile = tmp_path / 'pid'
    pidfile.write_text(f"{os.getpid()}\n")

    with pytest.raises(AlreadyRunningError) as exc:
        write_pidfile(str(pidfile))

    assert exc.value.pid == os.getpid()
    assert exc.value.path == str(pidfile)
    # The live owner's PID file must be left exactly as it was.
    assert pidfile.read_text() == f"{os.getpid()}\n"


@pytest.mark.parametrize('contents', ('', 'garbage\n'))
def test_write_pidfile_reclaims_unreadable(tmp_path, contents):
    pidfile = tmp_path / 'pid'
    pidfile.write_text(contents)

    write_pidfile(str(pidfile))

    assert pidfile.read_text() == f"{os.getpid()}\n"


def test_write_pidfile_reclaims_stale(tmp_path):
    pidfile = tmp_path / 'pid'
    pidfile.write_text(f"{make_dead_pid()}\n")

    write_pidfile(str(pidfile))

    assert pidfile.read_text() == f"{os.getpid()}\n"


def test_write_pidfile_other_oserror_propagates(tmp_path):
    # A missing parent directory is not an "already running" condition.
    with pytest.raises(FileNotFoundError):
        write_pidfile(str(tmp_path / 'missing' / 'pid'))


def test_write_pidfile_is_never_visible_empty(tmp_path, mocker):
    # The PID file must be fully written the instant it appears. A concurrent starter
    # that saw it empty would take it for a corrupt file and reclaim it, and both
    # daemons would then run against one private data directory.
    pidfile = tmp_path / 'pid'
    observed = []

    real_link = os.link

    def observing_link(src, dst):
        real_link(src, dst)
        # Stand in for the concurrent starter, which reaches this point by way of a
        # FileExistsError from its own creation attempt.
        observed.append(_reclaim_stale_pidfile(str(pidfile)))

    mocker.patch('ansible_runner.utils._daemonize.os.link', side_effect=observing_link)

    write_pidfile(str(pidfile))

    assert observed == [(False, os.getpid())]
    assert pidfile.read_text() == f"{os.getpid()}\n"


def test_write_pidfile_removes_its_temporary_file(tmp_path):
    write_pidfile(str(tmp_path / 'pid'))

    assert sorted(p.name for p in tmp_path.iterdir()) == ['pid']


def test_write_pidfile_removes_its_temporary_file_on_failure(tmp_path):
    pidfile = tmp_path / 'pid'
    pidfile.write_text(f"{os.getpid()}\n")

    with pytest.raises(AlreadyRunningError):
        write_pidfile(str(pidfile))

    assert sorted(p.name for p in tmp_path.iterdir()) == ['pid']


def test_write_pidfile_reuses_leftover_temporary_file(tmp_path):
    # A crash can leave a temporary file behind under a PID that is later recycled.
    pidfile = tmp_path / 'pid'
    (tmp_path / f"pid.{os.getpid()}").write_text('leftover junk that is longer than a pid\n')

    write_pidfile(str(pidfile))

    assert pidfile.read_text() == f"{os.getpid()}\n"


def test_write_pidfile_loses_reclaim_race(tmp_path, mocker):
    # If another process reclaims the stale PID file first, report that it is running
    # rather than looping or clobbering it.
    pidfile = tmp_path / 'pid'
    pidfile.write_text(f"{make_dead_pid()}\n")

    def racer(path):  # pylint: disable=W0613
        pidfile.write_text('4242\n')
        return True, None

    mocker.patch('ansible_runner.utils._daemonize._reclaim_stale_pidfile', side_effect=racer)

    with pytest.raises(AlreadyRunningError) as exc:
        write_pidfile(str(pidfile))

    assert exc.value.pid == 4242
    assert pidfile.read_text() == '4242\n'


def test_reclaim_stale_pidfile_missing(tmp_path):
    assert _reclaim_stale_pidfile(str(tmp_path / 'nope')) == (True, None)


def test_reclaim_stale_pidfile_removes_dead_owner(tmp_path):
    dead_pid = make_dead_pid()
    pidfile = tmp_path / 'pid'
    pidfile.write_text(f"{dead_pid}\n")

    assert _reclaim_stale_pidfile(str(pidfile)) == (True, dead_pid)
    assert not pidfile.exists()


def test_reclaim_stale_pidfile_keeps_live_owner(tmp_path):
    pidfile = tmp_path / 'pid'
    pidfile.write_text(f"{os.getpid()}\n")

    assert _reclaim_stale_pidfile(str(pidfile)) == (False, os.getpid())
    assert pidfile.exists()


def test_reclaim_stale_pidfile_detects_replacement(tmp_path, mocker):
    # A racing process can replace the PID file while we wait for the lock. Its
    # replacement must not be unlinked as though it were the stale file we opened.
    pidfile = tmp_path / 'pid'
    pidfile.write_text(f"{make_dead_pid()}\n")

    def replace(fd, operation):  # pylint: disable=W0613
        pidfile.unlink()
        pidfile.write_text(f"{os.getpid()}\n")

    mocker.patch('ansible_runner.utils._daemonize.fcntl.flock', side_effect=replace)

    assert _reclaim_stale_pidfile(str(pidfile)) == (True, None)
    assert pidfile.read_text() == f"{os.getpid()}\n"


def test_reclaim_stale_pidfile_without_locking(tmp_path, mocker):
    # Not every filesystem can lock; reclaiming must still work there.
    dead_pid = make_dead_pid()
    pidfile = tmp_path / 'pid'
    pidfile.write_text(f"{dead_pid}\n")

    mocker.patch('ansible_runner.utils._daemonize.fcntl.flock', side_effect=OSError)

    assert _reclaim_stale_pidfile(str(pidfile)) == (True, dead_pid)
    assert not pidfile.exists()


def test_ensure_stdio_fds_open_reopens_closed_descriptors():
    # Must run in a subprocess: closing pytest's own descriptors in-process is not safe.
    script = textwrap.dedent(
        '''
        import os
        from ansible_runner.utils._daemonize import _ensure_stdio_fds_open

        os.close(0)
        os.close(1)
        _ensure_stdio_fds_open()

        for fileno in (0, 1, 2):
            os.fstat(fileno)

        # The handshake pipe must not be handed a standard descriptor, which the
        # redirect performed later on would overwrite.
        read_fd, write_fd = os.pipe()
        assert read_fd > 2 and write_fd > 2, (read_fd, write_fd)
        '''
    )
    subprocess.run([sys.executable, '-c', script], check=True)


def test_remove_pidfile_own(tmp_path):
    pidfile = tmp_path / 'pid'
    pidfile.write_text(f"{os.getpid()}\n")

    remove_pidfile(str(pidfile))

    assert not pidfile.exists()


def test_remove_pidfile_other_owner(tmp_path):
    # A PID file we no longer own belongs to a daemon started after us.
    other_pid = make_dead_pid()
    pidfile = tmp_path / 'pid'
    pidfile.write_text(f"{other_pid}\n")

    remove_pidfile(str(pidfile))

    assert pidfile.read_text() == f"{other_pid}\n"


def test_remove_pidfile_missing(tmp_path):
    remove_pidfile(str(tmp_path / 'nope'))


def test_daemon_context_close_is_idempotent(tmp_path):
    pidfile = tmp_path / 'pid'
    pidfile.write_text(f"{os.getpid()}\n")

    context = DaemonContext(str(pidfile))
    assert context.is_open is False

    # close() on a context that was never opened must not touch the PID file.
    context.close()
    context.close()

    assert pidfile.exists()
