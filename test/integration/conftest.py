import os
import shutil

import pytest
import pexpect
from ansible_runner.config.runner import RunnerConfig


@pytest.fixture(scope='function')
def rc(tmpdir):
    rc = RunnerConfig(str(tmpdir))
    rc.suppress_ansible_output = True
    rc.expect_passwords = {
        pexpect.TIMEOUT: None,
        pexpect.EOF: None
    }
    rc.cwd = str(tmpdir)
    rc.env = {}
    rc.job_timeout = 10
    rc.idle_timeout = 0
    rc.pexpect_timeout = 2.
    rc.pexpect_use_poll = True
    return rc


# TODO: determine if we want to add docker / podman
# to zuul instances in order to run these tests
@pytest.fixture(scope="session", autouse=True)
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


# TODO: determine if we want to add docker / podman
# to zuul instances in order to run these tests
@pytest.fixture(scope="session")
def container_runtime_installed():
    import subprocess

    for runtime in ('podman', 'docker'):
        try:
            subprocess.run([runtime, '-v'])
            return runtime
        except FileNotFoundError:
            pass
    pytest.skip('No container runtime is available.')


@pytest.fixture(scope='session')
def clear_integration_artifacts(request):
    '''Fixture is session scoped to allow parallel runs without error
    '''
    if 'PYTEST_XDIST_WORKER' in os.environ:
        # we never want to clean artifacts if running parallel tests
        # because we cannot know when all processes are finished and it is
        # safe to clean up
        return

    def rm_integration_artifacts():
        path = "test/integration/artifacts"
        if os.path.exists(path):
            shutil.rmtree(path)

    request.addfinalizer(rm_integration_artifacts)
