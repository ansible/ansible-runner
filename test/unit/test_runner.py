# -*- coding: utf-8 -*-

import codecs
import os
import re

import mock
import pexpect
import pytest
import six

from ansible_runner import Runner
from ansible_runner.exceptions import CallbackError
from ansible_runner.runner_config import RunnerConfig

HERE, FILENAME = os.path.split(__file__)


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


@pytest.fixture(autouse=True)
def mock_sleep(request):
    # the handle_termination process teardown mechanism uses `time.sleep` to
    # wait on processes to respond to SIGTERM; these are tests and don't care
    # about being nice
    m = mock.patch('time.sleep')
    m.start()
    request.addfinalizer(m.stop)


def test_simple_spawn(rc):
    rc.command = ['ls', '-la']
    status, exitcode = Runner(config=rc).run()
    assert status == 'successful'
    assert exitcode == 0


def test_error_code(rc):
    rc.command = ['ls', '--nonsense']
    status, exitcode = Runner(config=rc).run()
    assert status == 'failed'
    assert exitcode > 0


def test_password_prompt(rc):
    rc.command = ['python', '-c' 'from __future__ import print_function; import time; print(input("Password: "))']
    rc.expect_passwords[re.compile(r'Password:\s*?$', re.M)] = '1234'
    status, exitcode = Runner(config=rc).run()
    assert status == 'successful'
    assert exitcode == 0
    with open(os.path.join(rc.artifact_dir, 'stdout')) as f:
        assert '1234' in f.read()


# TODO: matt does not like this test
def test_job_timeout(rc):
    rc.command = ['python', '-c', 'import time; time.sleep(5)']
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'timeout'
    assert runner.timed_out is True


def test_cancel_callback(rc):
    rc.command = ['python', '-c', 'print(input("Password: "))']
    status, exitcode = Runner(config=rc, cancel_callback=lambda: True).run()
    assert status == 'canceled'


def test_cancel_callback_error(rc):
    def kaboom():
        raise Exception('kaboom')

    rc.command = ['python', '-c', 'print(input("Password: "))']
    with pytest.raises(CallbackError):
        Runner(config=rc, cancel_callback=kaboom).run()


@pytest.mark.parametrize('value', ['abc123', six.u('Iñtërnâtiônàlizætiøn')])
def test_env_vars(rc, value):
    rc.command = ['python', '-c', 'import os; print(os.getenv("X_MY_ENV"))']
    rc.env = {'X_MY_ENV': value}
    status, exitcode = Runner(config=rc).run()
    assert status == 'successful'
    assert exitcode == 0
    with codecs.open(os.path.join(rc.artifact_dir, 'stdout'), 'r', encoding='utf-8') as f:
        assert value in f.read()
