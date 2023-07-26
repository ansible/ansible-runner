# -*- coding: utf-8 -*-

import os
import pytest

from ansible_runner.config.command import CommandConfig
from ansible_runner.config._base import BaseExecutionMode
from ansible_runner.exceptions import ConfigurationError


def test_ansible_config_defaults(tmp_path, patch_private_data_dir):
    # pylint: disable=W0613
    rc = CommandConfig()

    # Check that the private data dir is placed in our default location with our default prefix
    # and has some extra uniqueness on the end.
    base_private_data_dir = tmp_path.joinpath('.ansible-runner-').as_posix()
    assert rc.private_data_dir.startswith(base_private_data_dir)
    assert len(rc.private_data_dir) > len(base_private_data_dir)

    assert rc.execution_mode == BaseExecutionMode.NONE
    assert rc.runner_mode is None


def test_invalid_runner_mode_value():
    with pytest.raises(ConfigurationError) as exc:
        CommandConfig(runner_mode='test')

    assert "Invalid runner mode" in exc.value.args[0]


def test_prepare_run_command_interactive():
    rc = CommandConfig()
    executable_cmd = 'ansible-playbook'
    cmdline_args = ['main.yaml', '-i', 'test']
    rc.prepare_run_command(executable_cmd, cmdline_args=cmdline_args)
    expected_command = ['ansible-playbook', 'main.yaml', '-i', 'test']
    assert rc.command == expected_command
    assert rc.runner_mode == 'pexpect'
    assert rc.execution_mode == BaseExecutionMode.ANSIBLE_COMMANDS


def test_prepare_run_command_non_interactive():
    rc = CommandConfig()
    executable_cmd = 'ansible-doc'
    cmdline_args = ['-l']
    rc.prepare_run_command(executable_cmd, cmdline_args=cmdline_args)
    expected_command = ['ansible-doc', '-l']
    assert rc.command == expected_command
    assert rc.runner_mode == 'subprocess'
    assert rc.execution_mode == BaseExecutionMode.ANSIBLE_COMMANDS


def test_prepare_run_command_generic():
    rc = CommandConfig()
    executable_cmd = 'python3'
    cmdline_args = ['test.py']
    rc.prepare_run_command(executable_cmd, cmdline_args=cmdline_args)
    expected_command = ['python3', 'test.py']
    assert rc.command == expected_command
    assert rc.runner_mode == 'pexpect'
    assert rc.execution_mode == BaseExecutionMode.GENERIC_COMMANDS


@pytest.mark.parametrize('runtime', ('docker', 'podman'))
def test_prepare_run_command_with_containerization(tmp_path, runtime, mocker):
    mocker.patch.dict('os.environ', {'HOME': str(tmp_path)}, clear=True)
    tmp_path.joinpath('.ssh').mkdir()

    kwargs = {
        'private_data_dir': tmp_path,
        'process_isolation': True,
        'container_image': 'my_container',
        'process_isolation_executable': runtime
    }
    cwd = os.getcwd()
    executable_cmd = 'ansible-playbook'
    cmdline_args = ['main.yaml', '-i', cwd]
    rc = CommandConfig(**kwargs)
    rc.ident = 'foo'
    rc.prepare_run_command(executable_cmd, cmdline_args=cmdline_args)

    assert rc.runner_mode == 'pexpect'
    extra_container_args = []
    if runtime == 'podman':
        extra_container_args = ['--quiet']
    else:
        extra_container_args = [f'--user={os.getuid()}']

    expected_command_start = [
        runtime,
        'run',
        '--rm',
        '--tty',
        '--interactive',
        '--workdir',
        '/runner/project',
        '-v', f'{cwd}/:{cwd}/',
        '-v', f'{rc.private_data_dir}/.ssh/:/home/runner/.ssh/',
        '-v', f'{rc.private_data_dir}/.ssh/:/root/.ssh/',
    ]

    if os.path.exists('/etc/ssh/ssh_known_hosts'):
        expected_command_start.extend(['-v', '/etc/ssh/:/etc/ssh/'])

    if runtime == 'podman':
        expected_command_start.extend(['--group-add=root', '--ipc=host'])

    expected_command_start.extend([
        '-v', f'{rc.private_data_dir}/artifacts/:/runner/artifacts/:Z',
        '-v', f'{rc.private_data_dir}/:/runner/:Z',
        '--env-file', f'{rc.artifact_dir}/env.list',
    ])

    expected_command_start.extend(extra_container_args)

    expected_command_start.extend([
        '--name',
        'ansible_runner_foo',
        'my_container',
        executable_cmd,
    ])

    expected_command_start.extend(cmdline_args)

    assert expected_command_start == rc.command
