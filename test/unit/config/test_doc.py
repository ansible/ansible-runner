# -*- coding: utf-8 -*-

import os
import pytest

from ansible_runner.config.doc import DocConfig
from ansible_runner.config._base import BaseExecutionMode
from ansible_runner.exceptions import ConfigurationError
from ansible_runner.utils import get_executable_path


def test_ansible_doc_defaults(tmp_path, patch_private_data_dir):
    rc = DocConfig()

    # Check that the private data dir is placed in our default location with our default prefix
    # and has some extra uniqueness on the end.
    base_private_data_dir = tmp_path.joinpath('.ansible-runner-').as_posix()
    assert rc.private_data_dir.startswith(base_private_data_dir)
    assert len(rc.private_data_dir) > len(base_private_data_dir)

    assert rc.execution_mode == BaseExecutionMode.ANSIBLE_COMMANDS
    assert rc.runner_mode == 'subprocess'


def test_invalid_runner_mode_value():
    with pytest.raises(ConfigurationError) as exc:
        DocConfig(runner_mode='test')

    assert "Invalid runner mode" in exc.value.args[0]


def test_invalid_response_format_value():
    with pytest.raises(ConfigurationError) as exc:
        rc = DocConfig()
        plugin_names = ['copy', 'file']
        rc.prepare_plugin_docs_command(plugin_names, response_format='test')

    assert "Invalid response_format test, valid value is one of either json, human" == exc.value.args[0]


def test_invalid_plugin_name_value():
    with pytest.raises(ConfigurationError) as exc:
        rc = DocConfig()
        plugin_names = 'copy', 'file'
        rc.prepare_plugin_docs_command(plugin_names)

    assert "plugin_names should be of type list" in exc.value.args[0]


def test_prepare_plugin_docs_command():
    rc = DocConfig()
    plugin_names = ['copy', 'file']
    plugin_type = 'module'
    rc.prepare_plugin_docs_command(plugin_names, plugin_type=plugin_type, snippet=True, playbook_dir='/tmp/test')
    expected_command = [get_executable_path('ansible-doc'), '-s', '-t', 'module', '--playbook-dir', '/tmp/test', 'copy', 'file']
    assert rc.command == expected_command
    assert rc.runner_mode == 'subprocess'
    assert rc.execution_mode == BaseExecutionMode.ANSIBLE_COMMANDS


@pytest.mark.parametrize('runtime', ('docker', 'podman'))
def test_prepare_plugin_docs_command_with_containerization(tmp_path, runtime, mocker):
    mocker.patch.dict('os.environ', {'HOME': str(tmp_path)}, clear=True)
    tmp_path.joinpath('.ssh').mkdir()

    kwargs = {
        'private_data_dir': tmp_path,
        'process_isolation': True,
        'container_image': 'my_container',
        'process_isolation_executable': runtime
    }
    rc = DocConfig(**kwargs)
    rc.ident = 'foo'

    plugin_names = ['copy', 'file']
    plugin_type = 'module'
    rc.prepare_plugin_docs_command(plugin_names, plugin_type=plugin_type, snippet=True, playbook_dir='/tmp/test')

    assert rc.runner_mode == 'subprocess'
    extra_container_args = []

    if runtime == 'podman':
        extra_container_args = ['--quiet']
    else:
        extra_container_args = [f'--user={os.getuid()}']

    expected_command_start = [
        runtime,
        'run',
        '--rm',
        '--interactive',
        '--workdir',
        '/runner/project',
        '-v', '{}/.ssh/:/home/runner/.ssh/'.format(rc.private_data_dir),
        '-v', '{}/.ssh/:/root/.ssh/'.format(rc.private_data_dir),
    ]

    if runtime == 'podman':
        expected_command_start.extend(['--group-add=root', '--ipc=host'])

    expected_command_start.extend([
        '-v', '{}/artifacts/:/runner/artifacts/:Z'.format(rc.private_data_dir),
        '-v', '{}/:/runner/:Z'.format(rc.private_data_dir),
        '--env-file', '{}/env.list'.format(rc.artifact_dir),
    ])

    expected_command_start.extend(extra_container_args)

    expected_command_start.extend([
        '--name', 'ansible_runner_foo',
        'my_container',
        'ansible-doc',
        '-s',
        '-t', 'module',
        '--playbook-dir', '/tmp/test',
        'copy',
        'file',
    ])

    assert expected_command_start == rc.command


def test_prepare_plugin_list_command():
    rc = DocConfig()
    rc.prepare_plugin_list_command(list_files=True, plugin_type='module', playbook_dir='/tmp/test', module_path='/test/module')
    expected_command = [get_executable_path('ansible-doc'), '-F', '-t', 'module', '--playbook-dir', '/tmp/test', '-M', '/test/module']
    assert rc.command == expected_command
    assert rc.runner_mode == 'subprocess'
    assert rc.execution_mode == BaseExecutionMode.ANSIBLE_COMMANDS


@pytest.mark.parametrize('runtime', ('docker', 'podman'))
def test_prepare_plugin_list_command_with_containerization(tmp_path, runtime, mocker):
    mocker.patch.dict('os.environ', {'HOME': str(tmp_path)}, clear=True)
    tmp_path.joinpath('.ssh').mkdir()

    kwargs = {
        'private_data_dir': tmp_path,
        'process_isolation': True,
        'container_image': 'my_container',
        'process_isolation_executable': runtime
    }
    rc = DocConfig(**kwargs)
    rc.ident = 'foo'
    rc.prepare_plugin_list_command(list_files=True, plugin_type='module', playbook_dir='/tmp/test', module_path='/test/module')

    assert rc.runner_mode == 'subprocess'
    extra_container_args = []

    if runtime == 'podman':
        extra_container_args = ['--quiet']
    else:
        extra_container_args = [f'--user={os.getuid()}']

    expected_command_start = [
        runtime,
        'run',
        '--rm',
        '--interactive',
        '--workdir',
        '/runner/project',
        '-v', '{}/.ssh/:/home/runner/.ssh/'.format(rc.private_data_dir),
        '-v', '{}/.ssh/:/root/.ssh/'.format(rc.private_data_dir),
    ]

    if runtime == 'podman':
        expected_command_start.extend(['--group-add=root', '--ipc=host'])

    expected_command_start.extend([
        '-v', '{}/artifacts/:/runner/artifacts/:Z'.format(rc.private_data_dir),
        '-v', '{}/:/runner/:Z'.format(rc.private_data_dir),
        '--env-file', '{}/env.list'.format(rc.artifact_dir),
    ])

    expected_command_start.extend(extra_container_args)

    expected_command_start.extend([
        '--name', 'ansible_runner_foo',
        'my_container',
        'ansible-doc',
        '-F',
        '-t', 'module',
        '--playbook-dir', '/tmp/test',
        '-M', '/test/module'
    ])

    assert expected_command_start == rc.command
