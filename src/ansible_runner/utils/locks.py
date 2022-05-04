from contextlib import contextmanager
from fasteners import InterProcessLock
from ansible_runner.exceptions import ProcessLockException


class TimeoutProcessLock(InterProcessLock):

    @contextmanager
    def locked(self, timeout):
        ok = self.acquire(timeout=timeout)
        if not ok:
            raise ProcessLockException()
        try:
            yield
        finally:
            self.release()
