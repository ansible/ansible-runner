
import os
import re
import pexpect
import pytest
from ansible_runner import Runner

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
    rc.job_timeout = .1
    rc.idle_timeout = 0
    rc.pexpect_timeout = .1
    rc.pexpect_use_poll = True
    return rc


def test_password_prompt(rc):
    rc.command = ['python', '-c' 'from __future__ import print_function; import time; print(input("Password: "))']
    rc.expect_passwords[re.compile(r'Password:\s*?$', re.M)] = '1234'
    status, exitcode = Runner(config=rc).run()
    assert status == 'successful'
    assert exitcode == 0
    with open(os.path.join(rc.artifact_dir, 'stdout')) as f:
        assert '1234' in f.read()
