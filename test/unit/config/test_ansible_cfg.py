# -*- coding: utf-8 -*-

import os
import pytest

from tempfile import gettempdir

from ansible_runner.config.ansible_cfg import AnsibleCfgConfig
from ansible_runner.config._base import BaseExecutionMode
from ansible_runner.exceptions import ConfigurationError
from ansible_runner.utils import get_executable_path


def test_ansible_cfg_init_defaults():
    rc = AnsibleCfgConfig()

    # Check that the private data dir is placed in our default location with our default prefix
    # and has some extra uniqueness on the end.
    base_private_data_dir = os.path.join(gettempdir(), '.ansible-runner-')
    assert rc.private_data_dir.startswith(base_private_data_dir)
    assert len(rc.private_data_dir) > len(base_private_data_dir)

    assert rc.execution_mode == BaseExecutionMode.ANSIBLE_COMMANDS


def test_invalid_runner_mode_value():
    with pytest.raises(ConfigurationError) as exc:
        AnsibleCfgConfig(runner_mode='test')

    assert "Invalid runner mode" in exc.value.args[0]


def test_prepare_config_command():
    rc = AnsibleCfgConfig()
    rc.prepare_ansible_config_command('list', config_file='/tmp/ansible.cfg')
    expected_command = [get_executable_path('ansible-config'), 'list', '-c', '/tmp/ansible.cfg']
    assert rc.command == expected_command
    assert rc.runner_mode == 'subprocess'


def test_prepare_config_invalid_command():
    with pytest.raises(ConfigurationError) as exc:
        rc = AnsibleCfgConfig()
        rc.prepare_ansible_config_command('list', config_file='/tmp/ansible.cfg', only_changed=True)

    assert "only_changed is applicable for action 'dump'" == exc.value.args[0]


def test_prepare_config_invalid_action():
    with pytest.raises(ConfigurationError) as exc:
        rc = AnsibleCfgConfig()
        rc.prepare_ansible_config_command('test')

    assert "Invalid action test, valid value is one of either list, dump, view" == exc.value.args[0]


@pytest.mark.parametrize('container_runtime', ['docker', 'podman'])
def test_prepare_config_command_with_containerization(tmp_path, container_runtime, mocker):
    mocker.patch.dict('os.environ', {'HOME': str(tmp_path)}, clear=True)
    tmp_path.joinpath('.ssh').mkdir()

    kwargs = {
        'private_data_dir': tmp_path,
        'process_isolation': True,
        'container_image': 'my_container',
        'process_isolation_executable': container_runtime
    }
    rc = AnsibleCfgConfig(**kwargs)
    rc.ident = 'foo'
    rc.prepare_ansible_config_command('list', config_file='/tmp/ansible.cfg')

    assert rc.runner_mode == 'subprocess'
    extra_container_args = []
    if container_runtime == 'podman':
        extra_container_args = ['--quiet']
    else:
        extra_container_args = [f'--user={os.getuid()}']

    expected_command_start = [
        container_runtime,
        'run',
        '--rm',
        '--interactive',
        '--workdir',
        '/runner/project',
        '-v', '{}/.ssh/:/home/runner/.ssh/'.format(rc.private_data_dir),
    ]

    if container_runtime == 'podman':
        expected_command_start.extend(['--group-add=root', '--ipc=host'])

    expected_command_start.extend([
        '-v', '{}/artifacts/:/runner/artifacts/:Z'.format(rc.private_data_dir),
        '-v', '{}/:/runner/:Z'.format(rc.private_data_dir),
        '--env-file', '{}/env.list'.format(rc.artifact_dir),
    ])

    expected_command_start.extend(extra_container_args)

    expected_command_start.extend([
        '--name',
        'ansible_runner_foo',
        'my_container',
        'ansible-config',
        'list',
        '-c',
        '/tmp/ansible.cfg',
    ])

    assert expected_command_start == rc.command
