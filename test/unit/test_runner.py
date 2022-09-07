# -*- coding: utf-8 -*-

import codecs
import os

import json
import pexpect
import pytest
import six
import sys

from ansible_runner import Runner
from ansible_runner.exceptions import CallbackError, AnsibleRunnerException
from ansible_runner.config.runner import RunnerConfig


@pytest.fixture(scope='function')
def rc(request, tmp_path):
    rc = RunnerConfig(str(tmp_path))
    rc.suppress_ansible_output = True
    rc.expect_passwords = {
        pexpect.TIMEOUT: None,
        pexpect.EOF: None
    }
    rc.cwd = str(tmp_path)
    rc.env = {}
    rc.job_timeout = .5
    rc.idle_timeout = 0
    rc.pexpect_timeout = .1
    rc.pexpect_use_poll = True
    return rc


@pytest.fixture(autouse=True)
def mock_sleep(request, mocker):
    # the handle_termination process teardown mechanism uses `time.sleep` to
    # wait on processes to respond to SIGTERM; these are tests and don't care
    # about being nice
    m = mocker.patch('time.sleep')
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
    rc.command = [sys.executable, '-c', 'import time; time.sleep(5)']
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'timeout'
    assert runner.timed_out is True


def test_cancel_callback(rc):
    rc.command = [sys.executable, '-c', 'print(input("Password: "))']
    status, exitcode = Runner(config=rc, cancel_callback=lambda: True).run()
    assert status == 'canceled'


def test_cancel_callback_error(rc):
    def kaboom():
        raise Exception('kaboom')

    rc.command = [sys.executable, '-c', 'print(input("Password: "))']
    with pytest.raises(CallbackError):
        Runner(config=rc, cancel_callback=kaboom).run()


def test_verbose_event_created_time(rc):
    rc.command = ['echo', 'helloworld']
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    for event in runner.events:
        assert 'created' in event, event


@pytest.mark.parametrize('value', ['abc123', six.u('Iñtërnâtiônàlizætiøn')])
def test_env_vars(rc, value):
    rc.command = [sys.executable, '-c', 'import os; print(os.getenv("X_MY_ENV"))']
    rc.env = {'X_MY_ENV': value}
    status, exitcode = Runner(config=rc).run()
    assert status == 'successful'
    assert exitcode == 0
    with codecs.open(os.path.join(rc.artifact_dir, 'stdout'), 'r', encoding='utf-8') as f:
        assert value in f.read()


def test_event_callback_data_check(rc, mocker):
    rc.ident = "testident"
    rc.check_job_event_data = True
    runner = Runner(config=rc, remove_partials=False)
    runner.event_handler = mocker.Mock()

    with pytest.raises(AnsibleRunnerException) as exc:
        runner.event_callback(dict(uuid="testuuid", counter=0))

    assert "Failed to open ansible stdout callback plugin partial data" in str(exc)


def test_event_callback_interface_has_ident(rc, mocker):
    rc.ident = "testident"
    runner = Runner(config=rc, remove_partials=False)
    runner.event_handler = mocker.Mock()
    mocker.patch('codecs.open', mocker.mock_open(read_data=json.dumps(dict(event="test"))))
    chmod = mocker.patch('os.chmod', mocker.Mock())
    mocker.patch('os.mkdir', mocker.Mock())

    runner.event_callback(dict(uuid="testuuid", counter=0))
    assert runner.event_handler.call_count == 1
    runner.event_handler.assert_called_with(dict(
        runner_ident='testident', counter=0, uuid='testuuid', event='test',
        created=mocker.ANY
    ))
    chmod.assert_called_once()
    runner.status_callback("running")


def test_event_callback_interface_calls_event_handler_for_verbose_event(rc, mocker):
    rc.ident = "testident"
    event_handler = mocker.Mock()
    runner = Runner(config=rc, event_handler=event_handler)
    mocker.patch('os.mkdir', mocker.Mock())

    runner.event_callback(dict(uuid="testuuid", event='verbose', counter=0))
    assert event_handler.call_count == 1
    event_handler.assert_called_with(dict(
        runner_ident='testident', counter=0, uuid='testuuid', event='verbose',
        created=mocker.ANY
    ))


def test_status_callback_interface(rc, mocker):
    runner = Runner(config=rc)
    assert runner.status == 'unstarted'
    runner.status_handler = mocker.Mock()
    runner.status_callback("running")
    assert runner.status_handler.call_count == 1
    runner.status_handler.assert_called_with(dict(status='running', runner_ident=str(rc.ident)), runner_config=runner.config)
    assert runner.status == 'running'


@pytest.mark.parametrize('runner_mode', ['subprocess'])
@pytest.mark.filterwarnings("error")
def test_no_ResourceWarning_error(rc, runner_mode):
    """
    Test that no ResourceWarning error is propogated up with warnings-as-errors enabled.

    Not properly closing stdout/stderr in Runner.run() will cause a ResourceWarning
    error that is only seen when we treat warnings as an error.
    """
    rc.command = ['echo', 'Hello World']
    rc.runner_mode = runner_mode
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'successful'
