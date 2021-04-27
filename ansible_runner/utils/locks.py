from fasteners import InterProcessLock


class ProcessLockException():
    pass


class TimeoutProcessLock(InterProcessLock):

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.pop("timeout")
        super(*args, **kwargs)

    def __enter__(self):
        acq = self.acquire(timeout=self.timeout)
        if not acq:
            raise ProcessLockException
        return self
