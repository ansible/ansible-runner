import pytest
import pexpect
from ansible_runner.runner_config import RunnerConfig


@pytest.fixture(scope='function')
def rc(request, tmpdir):
    rc = RunnerConfig(str(tmpdir))
    rc.suppress_ansible_output = True
    rc.expect_passwords = {
        pexpect.TIMEOUT: None,
        pexpect.EOF: None
    }
    rc.cwd = str(tmpdir)
    rc.env = {}
    rc.job_timeout = 2
    rc.idle_timeout = 0
    rc.pexpect_timeout = .1
    rc.pexpect_use_poll = True
    return rc


# TODO: determine if we want to add docker / podman
# to zuul instances in order to run these tests
@pytest.fixture(scope="function")
def container_runtime_available():
    import subprocess
    import warnings

    runtimes_available = True
    for runtime in ('docker', 'podman'):
        try:
            subprocess.run([runtime, '-v'])
        except FileNotFoundError:
            warnings.warn(UserWarning(f"{runtime} not available"))
            runtimes_available = False
    return runtimes_available
