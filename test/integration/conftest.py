import os

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


@pytest.fixture
def data_directory():
    integration_base = os.path.split(__file__)[0]
    test_base = os.path.split(integration_base)[0]
    return os.path.join(test_base, 'data')
