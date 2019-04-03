
import json
import os
import re
import pytest
try:
    from unittest.mock import MagicMock
except ImportError:
    from mock import MagicMock
from ansible_runner import Runner

from ansible_runner.exceptions import AnsibleRunnerException


def test_password_prompt(rc):
    rc.command = ['python', '-c' 'from __future__ import print_function; import time; print(input("Password: "))']
    rc.expect_passwords[re.compile(r'Password:\s*?$', re.M)] = '1234'
    status, exitcode = Runner(config=rc).run()
    assert status == 'successful'
    assert exitcode == 0
    with open(os.path.join(rc.artifact_dir, 'stdout')) as f:
        assert '1234' in f.read()


def test_run_command(rc):
    rc.command = ['pwd']
    status, exitcode = Runner(config=rc).run()
    assert status == 'successful'
    assert exitcode == 0
    with open(os.path.join(rc.artifact_dir, 'command')) as f:
        data = json.load(f)
        assert data.get('command') == ['pwd']
        assert 'cwd' in data
        assert isinstance(data.get('env'), dict)


def test_run_command_finished_callback(rc):
    finished_callback = MagicMock()
    rc.command = ['pwd']
    runner = Runner(config=rc, finished_callback=finished_callback)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    finished_callback.assert_called_with(runner)


def test_run_command_explosive_finished_callback(rc):
    def boom(*args):
        raise Exception('boom')
    rc.command = ['pwd']
    runner = Runner(config=rc, finished_callback=boom)
    with pytest.raises(Exception):
        runner.run()


def test_run_command_explosive_cancel_callback(rc):
    def boom(*args):
        raise Exception('boom')
    rc.command = ['pwd']
    runner = Runner(config=rc, cancel_callback=boom)
    with pytest.raises(Exception):
        runner.run()


def test_run_command_cancel_callback(rc):
    def cancel(*args):
        return True
    rc.command = ['pwd']
    runner = Runner(config=rc, cancel_callback=cancel)
    status, exitcode = runner.run()
    assert status == 'canceled'
    assert exitcode == 0


def test_run_command_job_timeout(rc):
    rc.command = ['pwd']
    rc.job_timeout = 0.0000001
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'timeout'
    assert exitcode == 254


def test_run_command_idle_timeout(rc):
    rc.command = ['pwd']
    rc.idle_timeout = 0.0000001
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'timeout'
    assert exitcode == 254


def test_run_command_failed(rc):
    rc.command = ['false']
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'failed'
    assert exitcode == 1


def test_run_command_long_running(rc):
    rc.command = ['yes']
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'timeout'
    assert exitcode == 254


def test_run_command_long_running_children(rc):
    rc.command = ['bash', '-c', "(yes)"]
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'timeout'
    assert exitcode == 254


def test_run_command_events_missing(rc):
    rc.command = ['pwd']
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    with pytest.raises(AnsibleRunnerException):
        list(runner.events)


def test_run_command_stdout_missing(rc):
    rc.command = ['pwd']
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    os.unlink(os.path.join(runner.config.artifact_dir, 'stdout'))
    with pytest.raises(AnsibleRunnerException):
        list(runner.stdout)


def test_run_command_no_stats(rc):
    rc.command = ['pwd']
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    with pytest.raises(AnsibleRunnerException):
        runner.stats


def test_run_command_ansible(rc):
    rc.module = "debug"
    rc.host_pattern = "localhost"
    rc.prepare()
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    assert list(runner.events) != []
    assert runner.stats != {}
    assert list(runner.host_events('localhost')) != []
    stdout = runner.stdout
    assert stdout.read() != ""


def test_run_command_ansible_event_handler(rc):
    event_handler = MagicMock()
    status_handler = MagicMock()
    rc.module = "debug"
    rc.host_pattern = "localhost"
    rc.prepare()
    runner = Runner(config=rc, event_handler=event_handler, status_handler=status_handler)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    event_handler.assert_called()
    status_handler.assert_called()


def test_run_command_ansible_event_handler_failure(rc):
    def event_handler(*args):
        raise IOError()
    rc.module = "debug"
    rc.host_pattern = "localhost"
    rc.prepare()
    runner = Runner(config=rc, event_handler=event_handler)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0


def test_run_command_ansible_rotate_artifacts(rc):
    rc.module = "debug"
    rc.host_pattern = "localhost"
    rc.prepare()
    rc.rotate_artifacts = 1
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0


def test_get_fact_cache(rc):
    assert os.path.basename(rc.fact_cache) == 'fact_cache'
    rc.module = "setup"
    rc.host_pattern = "localhost"
    rc.prepare()
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    print(rc.cwd)
    assert os.path.exists(os.path.join(rc.artifact_dir, 'fact_cache'))
    assert os.path.exists(os.path.join(rc.artifact_dir, 'fact_cache', 'localhost'))
    data = runner.get_fact_cache('localhost')
    assert data


def test_set_fact_cache(rc):
    assert os.path.basename(rc.fact_cache) == 'fact_cache'
    rc.module = "debug"
    rc.module_args = "var=message"
    rc.host_pattern = "localhost"
    rc.prepare()
    runner = Runner(config=rc)
    runner.set_fact_cache('localhost', dict(message='hello there'))
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    print(rc.cwd)
    assert os.path.exists(os.path.join(rc.artifact_dir, 'fact_cache'))
    assert os.path.exists(os.path.join(rc.artifact_dir, 'fact_cache', 'localhost'))
    data = runner.get_fact_cache('localhost')
    assert data['message'] == 'hello there'
