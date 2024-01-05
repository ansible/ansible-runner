# -*- coding: utf-8 -*-

import json
import os
import re
import six
import sys
import time

from test.utils.common import iterate_timeout

import pytest

from ansible_runner import Runner, run
from ansible_runner.exceptions import AnsibleRunnerException


@pytest.mark.xfail(reason='Test is unstable')
def test_password_prompt(rc):
    rc.command = [sys.executable, '-c' 'import time; print(input("Password: "))']
    rc.expect_passwords[re.compile(r'Password:\s*?$', re.M)] = '1234'
    status, exitcode = Runner(config=rc).run()
    assert status == 'successful'
    assert exitcode == 0
    # stdout file can be subject to a race condition
    for _ in iterate_timeout(30.0, 'stdout file to be written with 1234 in it', interval=0.2):
        with open(os.path.join(rc.artifact_dir, 'stdout')) as f:
            if '1234' in f.read():
                break


def test_run_command(rc):
    rc.command = ['sleep', '1']
    status, exitcode = Runner(config=rc).run()
    assert status == 'successful'
    assert exitcode == 0
    with open(os.path.join(rc.artifact_dir, 'command')) as f:
        data = json.load(f)
        assert data.get('command') == ['sleep', '1']
        assert 'cwd' in data
        assert isinstance(data.get('env'), dict)


def test_run_command_with_unicode(rc):
    expected = '"utf-8-䉪ቒ칸ⱷ?噂폄蔆㪗輥"'
    if six.PY2:
        expected = expected.decode('utf-8')
    rc.command = ['echo', '"utf-8-䉪ቒ칸ⱷ?噂폄蔆㪗輥"']
    rc.envvars = {"䉪ቒ칸": "蔆㪗輥"}
    rc.prepare_env()
    status, exitcode = Runner(config=rc).run()
    assert status == 'successful'
    assert exitcode == 0
    with open(os.path.join(rc.artifact_dir, 'command')) as f:
        data = json.load(f)
        assert data.get('command') == ['echo', expected]
        assert 'cwd' in data
        assert isinstance(data.get('env'), dict)
        assert u"䉪ቒ칸" in data.get('env')


def test_run_command_finished_callback(rc, mocker):
    finished_callback = mocker.MagicMock()
    rc.command = ['sleep', '1']
    runner = Runner(config=rc, finished_callback=finished_callback)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    finished_callback.assert_called_with(runner)


def test_run_command_explosive_finished_callback(rc):
    def boom(*args):
        raise Exception('boom')
    rc.command = ['sleep', '1']
    runner = Runner(config=rc, finished_callback=boom)
    with pytest.raises(Exception):
        runner.run()


def test_run_command_explosive_cancel_callback(rc):
    def boom(*args):
        raise Exception('boom')
    rc.command = ['sleep', '1']
    runner = Runner(config=rc, cancel_callback=boom)
    with pytest.raises(Exception):
        runner.run()


def test_run_command_cancel_callback(rc):
    def cancel(*args):
        return True
    rc.command = ['sleep', '1']
    runner = Runner(config=rc, cancel_callback=cancel)
    status, exitcode = runner.run()
    assert status == 'canceled'
    assert exitcode == 254


def test_run_command_job_timeout(rc):
    rc.command = ['sleep', '1']
    rc.job_timeout = 0.0000001
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'timeout'
    assert exitcode == 254


def test_run_command_idle_timeout(rc):
    rc.command = ['sleep', '1']
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


def test_executable_not_found(rc):
    rc.command = ['supercalifragilistic']
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'failed'
    assert exitcode == 127
    events = list(runner.events)
    assert len(events) == 1
    assert 'The command was not found or was not executable: supercalifragilistic' in events[0]['stdout']  # noqa


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
    rc.command = ['sleep', '1']
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    assert list(runner.events) == []


def test_run_command_stdout_missing(rc):
    rc.command = ['sleep', '1']
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    os.unlink(os.path.join(runner.config.artifact_dir, 'stdout'))
    with pytest.raises(AnsibleRunnerException):
        list(runner.stdout)


def test_run_command_no_stats(rc):
    rc.command = ['sleep', '1']
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    assert status == 'successful'
    assert exitcode == 0
    assert runner.stats is None


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
    assert list(runner.host_events('localhost')) != [], repr(list(runner.events))
    stdout = runner.stdout
    assert stdout.read() != ""


def test_run_command_ansible_event_handler(rc, mocker):
    event_handler = mocker.MagicMock()
    status_handler = mocker.MagicMock()
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


def test_set_extra_vars(rc):
    rc.module = "debug"
    rc.module_args = "var=test_extra_vars"
    rc.host_pattern = "localhost"
    rc.extra_vars = dict(test_extra_vars='hello there')
    rc.prepare()
    runner = Runner(config=rc)
    status, exitcode = runner.run()
    # stdout file can be subject to a race condition
    for _ in iterate_timeout(30.0, 'stdout file to be written with "hello there" in it', interval=0.2):
        with open(os.path.join(rc.artifact_dir, 'stdout')) as f:
            if 'hello there' in f.read():
                break


# regression test for https://github.com/ansible/ansible-runner/issues/1330
def test_pexpect_timeout(project_fixtures):
    r = run(
        private_data_dir=str(project_fixtures / 'pexpect_timeout_data_loss'),
        playbook='pb.yml',
        settings={"pexpect_timeout": 0.1},  # set the pexpect timeout very low
        cancel_callback=lambda: time.sleep(3) or False,  # induce enough delay in the child polling loop that the child will exit before being polled again
    )

    # ensure we got playbook_on_stats; if pexpect ate it, we won't...
    assert any(ev for ev in r.events if ev.get('event', None) == 'playbook_on_stats')
