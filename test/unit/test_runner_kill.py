# -*- coding: utf-8 -*-

from subprocess import PIPE

import pytest

from ansible_runner.runner import Runner


@pytest.mark.parametrize('runtime', ('docker', 'podman', 'container'))
def test_kill_container_uses_runtime_kill_command(mocker, runtime):
    process = mocker.Mock()
    process.communicate.return_value = (b'', b'')
    process.returncode = 0

    popen = mocker.patch('ansible_runner.runner.Popen')
    popen.return_value.__enter__.return_value = process
    popen.return_value.__exit__.return_value = None

    config = mocker.Mock()
    config.container_name = 'ansible_runner_foo'
    config.process_isolation_executable = runtime

    Runner(config=config).kill_container()

    popen.assert_called_once_with([runtime, 'kill', 'ansible_runner_foo'], stdout=PIPE, stderr=PIPE)


def test_kill_container_skips_when_container_name_missing(mocker):
    popen = mocker.patch('ansible_runner.runner.Popen')

    config = mocker.Mock()
    config.container_name = ''
    config.process_isolation_executable = 'container'

    Runner(config=config).kill_container()

    popen.assert_not_called()
