'''
Minimal, dependency free POSIX daemonization support.

This module is private to ``ansible_runner`` and covers only what the
``ansible-runner start`` command needs. It is not part of the public API.
'''

from __future__ import annotations

import atexit
import errno
import fcntl
import logging
import os
import resource
import signal
import sys

from collections.abc import Iterable
from types import FrameType, TracebackType
from typing import Any, NoReturn


__all__ = ['AlreadyRunningError', 'DaemonContext', 'read_pidfile']

# Requested mode of the PID file, subject to the umask of the invoking process. Matches
# the mode used by the ``lockfile`` package that ``python-daemon`` relied on, so that PID
# files written by older versions of ansible-runner still look the same.
PIDFILE_MODE = 0o644

STDIN_FILENO = 0
STDOUT_FILENO = 1
STDERR_FILENO = 2


class AlreadyRunningError(RuntimeError):
    '''
    Raised when a live process already owns a PID file.
    '''

    def __init__(self, path: str, pid: int | None = None) -> None:
        self.path = path
        self.pid = pid
        if pid is None:
            message = f"a process already owns the PID file {path}"
        else:
            message = f"a process is already running with PID {pid} (PID file {path})"
        super().__init__(message)


def read_pidfile(path: str) -> int | None:
    '''
    Read the PID recorded in a PID file.

    :param str path: Path of the PID file.

    :return: The recorded PID, or ``None`` if the file is missing, unreadable, or does
        not start with a decimal integer.
    '''
    try:
        with open(path, 'r') as f:
            return int(f.readline().strip())
    except (OSError, ValueError):
        return None


def pid_is_running(pid: int) -> bool:
    '''
    Determine whether a process exists.

    :param int pid: Process ID to test.

    :return: ``True`` if a process with that PID exists, otherwise ``False``.
    '''
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        # The process exists, we are simply not allowed to signal it. This clause must
        # come first: PermissionError is a subclass of OSError.
        pass
    except OSError:
        return False
    return True


def _is_same_file(fd: int, path: str) -> bool:
    '''
    Determine whether an open descriptor and a path still refer to the same file.

    :param int fd: Open file descriptor.
    :param str path: Path to compare it against.
    '''
    try:
        by_fd = os.fstat(fd)
        by_path = os.stat(path)
    except OSError:
        return False
    return (by_fd.st_dev, by_fd.st_ino) == (by_path.st_dev, by_path.st_ino)


def _reclaim_stale_pidfile(path: str) -> tuple[bool, int | None]:
    '''
    Remove a PID file if the process that recorded it no longer exists.

    An exclusive ``flock`` serializes this against other processes running the same code.
    Reading the PID and unlinking the file are separate operations, so without the lock
    two daemons starting at once could both decide the same PID file is stale and go on
    to delete each other's replacement, leaving both running against a single private
    data directory with only the second one recorded.

    :param str path: Path of the PID file to examine.

    :return: ``(reclaimed, pid)``, where ``reclaimed`` says whether the caller should
        retry creating the PID file, and ``pid`` is the live owner when it should not.
    '''
    try:
        fd = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return True, None

    try:
        try:
            # Blocking, deliberately. The lock is only ever held across the handful of
            # syscalls below, and waiting for the holder to finish is what lets us
            # report its PID accurately instead of a PID we already know to be dead.
            fcntl.flock(fd, fcntl.LOCK_EX)
        except OSError:
            # Not every filesystem can lock. Carry on unserialized, which is still an
            # improvement on never reclaiming the file at all.
            pass
        else:
            # Whoever held the lock before us may have replaced the file entirely.
            if not _is_same_file(fd, path):
                return True, None

        pid = read_pidfile(path)
        if pid is not None and pid_is_running(pid):
            return False, pid

        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        return True, pid
    finally:
        os.close(fd)


def _create_pidfile(path: str) -> bool:
    '''
    Atomically create a fully written PID file, if the path is free.

    The PID is written to a uniquely named temporary file alongside the target and then
    hard linked into place. ``os.link()`` is atomic and fails if the destination exists,
    so this gives the same exclusivity as ``O_CREAT | O_EXCL`` while additionally
    guaranteeing that the PID file is never observable as an empty file. That matters
    because ``_reclaim_stale_pidfile()`` treats an unreadable PID file as stale: with a
    plain exclusive create, a process starting concurrently could look in between our
    create and our write, and delete the PID file out from under us.

    :param str path: Path of the PID file to create.

    :return: ``True`` on success, ``False`` if the PID file already exists.
    '''
    # No other live process can share our PID, so this name is ours alone.
    tmp = f"{path}.{os.getpid()}"
    try:
        fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, PIDFILE_MODE)
        with os.fdopen(fd, 'w') as f:
            f.write(f"{os.getpid()}\n")

        # The mode of the temporary file carries over: link() creates a second name for
        # the same inode rather than a new file.
        try:
            os.link(tmp, path)
        except FileExistsError:
            return False
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def write_pidfile(path: str) -> None:
    '''
    Atomically create a PID file recording the PID of the calling process.

    A PID file left behind by a process that no longer exists (killed with ``SIGKILL``,
    host reboot, ...) is treated as stale, removed, and the creation retried once.

    :param str path: Path of the PID file to create.

    :raises AlreadyRunningError: If a live process already owns the PID file.
    '''
    for final_attempt in (False, True):
        if _create_pidfile(path):
            return
        if final_attempt:
            # Another process reclaimed the PID file before we could, so it is in use.
            raise AlreadyRunningError(path, read_pidfile(path))
        reclaimed, pid = _reclaim_stale_pidfile(path)
        if not reclaimed:
            raise AlreadyRunningError(path, pid)


def remove_pidfile(path: str) -> None:
    '''
    Remove a PID file, but only if it still records the PID of the calling process.

    The ownership check matters because ``ansible-runner stop`` removes the PID file
    itself before the daemon has finished dying: without it, a late running exit handler
    could delete the PID file of a daemon started in the meantime.

    :param str path: Path of the PID file to remove.
    '''
    if read_pidfile(path) != os.getpid():
        return
    try:
        os.unlink(path)
    except OSError:
        pass


def _ensure_stdio_fds_open() -> None:
    '''
    Make sure descriptors 0, 1 and 2 are open, attaching them to the null device if not.

    ``os.pipe()`` and ``os.open()`` hand out the lowest free descriptors. If we were
    invoked with, say, standard output closed, the start-up handshake pipe would be
    allocated descriptor 1 and then destroyed by ``_redirect_std_streams()`` before the
    daemon had a chance to report anything, silently losing the report.
    '''
    for fileno in (STDIN_FILENO, STDOUT_FILENO, STDERR_FILENO):
        try:
            os.fstat(fileno)
        except OSError as exc:
            # Only EBADF means the descriptor is free. Anything else is a live but
            # unhappy descriptor, which we must not replace with the null device.
            if exc.errno != errno.EBADF:
                raise
            fd = os.open(os.devnull, os.O_RDWR)
            if fd != fileno:
                os.dup2(fd, fileno)
                os.close(fd)


def _flush_std_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (AttributeError, ValueError, OSError):
            pass


def _redirect_std_streams(stdout: str | None, stderr: str | None) -> None:
    '''
    Detach the standard streams from whatever the launching process was using.

    File descriptors 0, 1 and 2 are targeted directly rather than ``sys.std*.fileno()``
    because those objects may have been replaced (by a test harness, for example) and
    may not be backed by the real descriptors at all.

    :param stdout: File to append standard output to, or ``None`` for the null device.
    :param stderr: File to append standard error to, or ``None`` for the null device.
    '''
    _flush_std_streams()

    devnull = os.open(os.devnull, os.O_RDWR)
    try:
        os.dup2(devnull, STDIN_FILENO)
        for path, fileno in ((stdout, STDOUT_FILENO), (stderr, STDERR_FILENO)):
            if path is None:
                os.dup2(devnull, fileno)
                continue
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.dup2(fd, fileno)
            finally:
                if fd > STDERR_FILENO:
                    os.close(fd)
    finally:
        if devnull > STDERR_FILENO:
            os.close(devnull)

    # Rebind the Python level objects too. Anything still holding the launcher's original
    # stream objects would otherwise keep writing to them, which only happens to be
    # harmless when those objects are backed by the descriptors redirected above.
    old_stdout, old_stderr = sys.stdout, sys.stderr

    # Line buffered, because the daemon is normally reaped with SIGKILL: ``stop`` calls
    # Runner.handle_termination(), which does os.killpg(..., SIGKILL). A block buffered
    # stream would discard up to a bufferful of the log file it was pointed at, and
    # nothing would be tailable while a job runs.
    #
    # These deliberately outlive this function.
    # pylint: disable=R1732
    sys.stdin = open(STDIN_FILENO, 'r', closefd=False)
    sys.stdout = open(STDOUT_FILENO, 'w', buffering=1, closefd=False)
    sys.stderr = open(STDERR_FILENO, 'w', buffering=1, closefd=False)

    _repoint_logging_streams(((old_stdout, sys.stdout), (old_stderr, sys.stderr)))


def _repoint_logging_streams(replacements: Iterable[tuple[Any, Any]]) -> None:
    '''
    Point logging handlers that captured the launcher's stream objects at their
    replacements.

    Handlers configured before detaching hold a direct reference to the old objects, so
    rebinding ``sys.stdout``/``sys.stderr`` is not on its own enough to stop them writing
    to whatever the launcher was using.

    :param replacements: Pairs of (old stream, new stream).
    '''
    loggers: list[Any] = [logging.root, *logging.Logger.manager.loggerDict.values()]
    for logger in loggers:
        for handler in getattr(logger, 'handlers', ()):
            if not isinstance(handler, logging.StreamHandler):
                continue
            for old, new in replacements:
                if handler.stream is old:
                    handler.setStream(new)
                    break


def _terminate(signal_number: int, frame: FrameType | None) -> NoReturn:
    # pylint: disable=W0613
    raise SystemExit(f"Terminating on signal {signal_number}")


def _set_signal_handlers() -> None:
    '''
    Install the signal dispositions a daemon is expected to have.

    ``SIGTERM`` is turned into ``SystemExit`` so that the ``with`` block and the
    ``atexit`` handlers get a chance to remove the PID file, and the job control signals
    are ignored so that a stray ``SIGTSTP`` cannot suspend the daemon.
    '''
    for name in ('SIGTSTP', 'SIGTTIN', 'SIGTTOU'):
        number = getattr(signal, name, None)
        if number is not None:
            signal.signal(number, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, _terminate)


def _report_to_launcher(write_fd: int, message: str) -> None:
    '''
    Send a start-up report to the launching process and close the pipe.

    An empty message means the daemon started successfully.
    '''
    try:
        if message:
            os.write(write_fd, message.encode('utf-8', errors='replace'))
    except OSError:
        pass
    finally:
        try:
            os.close(write_fd)
        except OSError:
            pass


def _exit_launcher(read_fd: int) -> NoReturn:
    '''
    Wait for the daemon's start-up report, then terminate the launching process.

    ``os._exit()`` is deliberate. This process is a fork parent that shares its entire
    state with the daemon: ``atexit`` handlers (``utils.register_for_cleanup()`` deletes
    the private data directory!), ``multiprocessing`` bookkeeping, and duplicated stdio
    buffers. Unwinding the stack with ``sys.exit()`` would run all of that a second time
    against state the daemon now owns.
    '''
    chunks: list[bytes] = []
    try:
        while True:
            data = os.read(read_fd, 4096)
            if not data:
                break
            chunks.append(data)
    except OSError:
        pass
    finally:
        os.close(read_fd)

    message = b''.join(chunks).decode('utf-8', errors='replace').strip()
    if message:
        try:
            sys.stderr.write(f"{message}\n")
            sys.stderr.flush()
        except (AttributeError, ValueError, OSError):
            pass
        os._exit(1)  # pylint: disable=W0212
    os._exit(0)  # pylint: disable=W0212


class DaemonContext:
    '''
    Turn the calling process into a POSIX daemon for the duration of a ``with`` block.

    This is a small, dependency free stand-in for ``daemon.DaemonContext`` covering only
    what ``ansible-runner start`` needs.

    Entering the context forks twice with an ``os.setsid()`` in between. The process that
    entered the context never leaves ``__enter__()``: it waits for the daemon to report
    that it has started, writes any failure to standard error, and exits with 0 on
    success or 1 on failure. Only the daemon returns from ``__enter__()``.

    The resulting process group contains the daemon and its descendants and nothing else,
    which is what lets ``Runner.handle_termination()`` signal the whole job with
    ``os.killpg()``.
    '''

    def __init__(self,
                 pidfile: str,
                 working_directory: str = '/',
                 stdout: str | None = None,
                 stderr: str | None = None,
                 umask: int | None = None) -> None:
        '''
        :param str pidfile: Path of the PID file to create once detached.
        :param str working_directory: Directory to change to, so that the daemon does not
            keep a file system busy. Defaults to the root directory.
        :param stdout: File to append the daemon's standard output to, or ``None`` to
            discard it.
        :param stderr: File to append the daemon's standard error to, or ``None`` to
            discard it.
        :param umask: File mode creation mask to set, or ``None`` to inherit the mask of
            the launching process.
        '''
        self.pidfile = pidfile
        self.working_directory = working_directory
        self.stdout = stdout
        self.stderr = stderr
        self.umask = umask
        self._is_open = False

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(self) -> None:
        '''
        Detach from the launching process and claim the PID file.

        :raises AlreadyRunningError: In the daemon process only, if the PID file is
            already owned. The launching process reports it on standard error instead.
        '''
        if self._is_open:
            return

        # Before allocating anything: the handshake pipe must not land on a standard
        # descriptor that the redirect below would then overwrite.
        _ensure_stdio_fds_open()

        # Buffers are duplicated by fork(); flush now so nothing is written twice.
        _flush_std_streams()

        read_fd, write_fd = os.pipe()

        if os.fork() > 0:
            os.close(write_fd)
            _exit_launcher(read_fd)

        os.close(read_fd)
        try:
            # Become a session leader so the daemon has no controlling terminal, then
            # fork again so the daemon is not a session leader and can never acquire one.
            os.setsid()
            if os.fork() > 0:
                os._exit(0)  # pylint: disable=W0212

            os.chdir(self.working_directory)
            if self.umask is not None:
                os.umask(self.umask)
            # The daemon may hold vault passwords in memory, so do not dump core.
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            _set_signal_handlers()
            _redirect_std_streams(self.stdout, self.stderr)
            write_pidfile(self.pidfile)
        except BaseException as exc:
            _report_to_launcher(write_fd, str(exc) or exc.__class__.__name__)
            os._exit(1)  # pylint: disable=W0212

        _report_to_launcher(write_fd, '')
        self._is_open = True
        atexit.register(self.close)

    def close(self) -> None:
        '''
        Release the PID file. Safe to call more than once.
        '''
        if not self._is_open:
            return
        self._is_open = False
        remove_pidfile(self.pidfile)

    def __enter__(self) -> DaemonContext:
        self.open()
        return self

    def __exit__(self,
                 exc_type: type[BaseException] | None,
                 exc_value: BaseException | None,
                 exc_tb: TracebackType | None) -> None:
        self.close()
