# -*- coding: utf-8 -*-

import codecs
import os

import json
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


def test_event_callback_interface_has_ident(rc):
    rc.ident = "testident"
    runner = Runner(config=rc, remove_partials=False)
    runner.event_handler = mock.Mock()
    with mock.patch('codecs.open', mock.mock_open(read_data=json.dumps(dict(event="test")))):
        with mock.patch('os.chmod', mock.Mock()) as chmod:
            with mock.patch('os.mkdir', mock.Mock()):
                runner.event_callback(dict(uuid="testuuid", counter=0))
    assert runner.event_handler.call_count == 1
    runner.event_handler.assert_called_with(dict(runner_ident='testident', counter=0, uuid='testuuid', event='test'))
    chmod.assert_called_once()
    runner.status_callback("running")


def test_event_callback_interface_calls_event_handler_for_verbose_event(rc):
    rc.ident = "testident"
    event_handler = mock.Mock()
    runner = Runner(config=rc, event_handler=event_handler)
    with mock.patch('os.mkdir', mock.Mock()):
        runner.event_callback(dict(uuid="testuuid", event='verbose', counter=0))
    assert event_handler.call_count == 1
    event_handler.assert_called_with(dict(runner_ident='testident', counter=0, uuid='testuuid', event='verbose'))


def test_status_callback_interface(rc):
    runner = Runner(config=rc)
    assert runner.status == 'unstarted'
    runner.status_handler = mock.Mock()
    runner.status_callback("running")
    assert runner.status_handler.call_count == 1
    runner.status_handler.assert_called_with(dict(status='running', runner_ident=str(rc.ident)), runner_config=runner.config)
    assert runner.status == 'running'
