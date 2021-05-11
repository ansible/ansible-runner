# -*- coding: utf-8 -*-

import os
import pytest

from ansible_runner.config.inventory import InventoryConfig
from ansible_runner.config._base import BaseExecutionMode
from ansible_runner.exceptions import ConfigurationError
from ansible_runner.utils import get_executable_path


def test_ansible_inventory_init_defaults():
    rc = InventoryConfig()
    assert rc.private_data_dir == os.path.abspath(os.path.expanduser('~/.ansible-runner'))
    assert rc.execution_mode == BaseExecutionMode.ANSIBLE_COMMANDS


def test_invalid_runner_mode_value():
    with pytest.raises(ConfigurationError) as exc:
        InventoryConfig(runner_mode='test')

    assert "Invalid runner mode" in exc.value.args[0]


def test_prepare_inventory_command():
    rc = InventoryConfig()
    inventories = ['/tmp/inventory1', '/tmp/inventory2']
    rc.prepare_inventory_command('list', inventories, response_format='yaml', playbook_dir='/tmp',
                                 vault_ids='1234', vault_password_file='/tmp/password')
    expected_command = [get_executable_path('ansible-inventory'), '--list', '-i', '/tmp/inventory1', '-i', '/tmp/inventory2', '--yaml', '--playbook-dir'] + \
                       ['/tmp', '--vault-id', '1234', '--vault-password-file', '/tmp/password']
    assert rc.command == expected_command
    assert rc.runner_mode == 'subprocess'


def test_prepare_inventory_invalid_action():
    with pytest.raises(ConfigurationError) as exc:
        rc = InventoryConfig()
        inventories = ['/tmp/inventory1', '/tmp/inventory2']
        rc.prepare_inventory_command('test', inventories=inventories)

    assert "Invalid action test, valid value is one of either graph, host, list" == exc.value.args[0]


def test_prepare_inventory_invalid_response_format():
    with pytest.raises(ConfigurationError) as exc:
        rc = InventoryConfig()
        inventories = ['/tmp/inventory1', '/tmp/inventory2']
        rc.prepare_inventory_command('list', inventories=inventories, response_format='test')

    assert "Invalid response_format test, valid value is one of either json, yaml, toml" == exc.value.args[0]


def test_prepare_inventory_invalid_inventories():
    with pytest.raises(ConfigurationError) as exc:
        rc = InventoryConfig()
        inventories = '/tmp/inventory1'
        rc.prepare_inventory_command('list', inventories=inventories)

    assert "inventories should be of type list" in exc.value.args[0]


def test_prepare_inventory_invalid_host_action():
    with pytest.raises(ConfigurationError) as exc:
        rc = InventoryConfig()
        inventories = ['/tmp/inventory1', '/tmp/inventory2']
        rc.prepare_inventory_command('host', inventories=inventories)

    assert "Value of host parameter is required when action in 'host'" == exc.value.args[0]


def test_prepare_inventory_invalid_graph_response_format():
    with pytest.raises(ConfigurationError) as exc:
        rc = InventoryConfig()
        inventories = ['/tmp/inventory1', '/tmp/inventory2']
        rc.prepare_inventory_command('graph', inventories=inventories, response_format='toml')

    assert "'graph' action supports only 'json' response format" == exc.value.args[0]


@pytest.mark.parametrize('container_runtime', ['docker', 'podman'])
def test_prepare_inventory_command_with_containerization(tmpdir, container_runtime):
    kwargs = {
        'private_data_dir': tmpdir,
        'process_isolation': True,
        'container_image': 'my_container',
        'process_isolation_executable': container_runtime
    }
    rc = InventoryConfig(**kwargs)
    rc.ident = 'foo'
    inventories = ['/tmp/inventory1', '/tmp/inventory2']
    rc.prepare_inventory_command('list', inventories, response_format='yaml', playbook_dir='/tmp',
                                 vault_ids='1234', vault_password_file='/tmp/password', output_file='/tmp/inv_out.txt',
                                 export=True)

    assert rc.runner_mode == 'subprocess'
    extra_container_args = []
    if container_runtime == 'podman':
        extra_container_args = ['--quiet']
    else:
        extra_container_args = ['--user={os.getuid()}']

    expected_command_start = [container_runtime, 'run', '--rm', '--interactive', '--workdir', '/runner/project'] + \
                             ['-v', '{}/.ssh/:/home/runner/.ssh/'.format(os.environ['HOME'])]
    if container_runtime == 'podman':
        expected_command_start +=['--group-add=root', '--userns=keep-id', '--ipc=host']

    expected_command_start += ['-v', '{}/artifacts/:/runner/artifacts:Z'.format(rc.private_data_dir)] + \
        ['-v', '{}/:/runner:Z'.format(rc.private_data_dir)] + \
        ['--env-file', '{}/env.list'.format(rc.artifact_dir)] + \
        extra_container_args + \
        ['--name', 'ansible_runner_foo', 'my_container'] + \
        ['ansible-inventory', '--list', '-i', '/tmp/inventory1', '-i', '/tmp/inventory2', '--yaml', '--playbook-dir'] + \
        ['/tmp', '--vault-id', '1234', '--vault-password-file', '/tmp/password', '--output', '/tmp/inv_out.txt'] + \
        ['--export']

    assert len(expected_command_start) == len(rc.command)

    for index, element in enumerate(expected_command_start):
        if '--user=' in element:
            assert '--user=' in rc.command[index]
        else:
            assert rc.command[index] == element
