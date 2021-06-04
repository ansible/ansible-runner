# -*- coding: utf-8 -*-

from functools import partial
import os
import re

import six
from pexpect import TIMEOUT, EOF

import pytest
from unittest.mock import (Mock, patch, PropertyMock)

from ansible_runner.config._base import BaseConfig, BaseExecutionMode
from ansible_runner.loader import ArtifactLoader
from ansible_runner.exceptions import ConfigurationError

try:
    Pattern = re._pattern_type
except AttributeError:
    # Python 3.7
    Pattern = re.Pattern


def load_file_side_effect(path, value=None, *args, **kwargs):
    if args[0] == path:
        if value:
            return value
    raise ConfigurationError


def test_base_config_init_defaults():
    rc = BaseConfig(private_data_dir='/tmp')
    assert rc.private_data_dir == '/tmp'
    assert rc.ident is not None
    assert rc.process_isolation is False
    assert rc.fact_cache_type == 'jsonfile'
    assert rc.json_mode is False
    assert rc.quiet is False
    assert rc.quiet is False
    assert rc.rotate_artifacts == 0
    assert rc.artifact_dir == os.path.join('/tmp/artifacts/%s' % rc.ident)
    assert isinstance(rc.loader, ArtifactLoader)


def test_base_config_with_artifact_dir():
    rc = BaseConfig(artifact_dir='/tmp/this-is-some-dir')
    assert rc.artifact_dir == os.path.join('/tmp/this-is-some-dir', rc.ident)
    assert rc.private_data_dir == os.path.abspath(os.path.expanduser('~/.ansible-runner'))


def test_base_config_init_with_ident():
    rc = BaseConfig(private_data_dir='/tmp', ident='test')
    assert rc.private_data_dir == '/tmp'
    assert rc.ident == 'test'
    assert rc.artifact_dir == os.path.join('/tmp/artifacts/test')
    assert isinstance(rc.loader, ArtifactLoader)


def test_base_config_project_dir():
    rc = BaseConfig(private_data_dir='/tmp', project_dir='/another/path')
    assert rc.project_dir == '/another/path'
    rc = BaseConfig(private_data_dir='/tmp')
    assert rc.project_dir == '/tmp/project'


def test_prepare_environment_vars_only_strings():
    rc = BaseConfig(private_data_dir="/tmp", envvars=dict(D='D'))

    value = dict(A=1, B=True, C="foo")
    envvar_side_effect = partial(load_file_side_effect, 'env/envvars', value)

    with patch.object(rc.loader, 'load_file', side_effect=envvar_side_effect):
        rc._prepare_env()
        assert 'A' in rc.env
        assert isinstance(rc.env['A'], six.string_types)
        assert 'B' in rc.env
        assert isinstance(rc.env['B'], six.string_types)
        assert 'C' in rc.env
        assert isinstance(rc.env['C'], six.string_types)
        assert 'D' in rc.env
        assert rc.env['D'] == 'D'


def test_prepare_environment_pexpect_defaults():
    rc = BaseConfig(private_data_dir="/tmp")
    rc._prepare_env()

    assert len(rc.expect_passwords) == 2
    assert TIMEOUT in rc.expect_passwords
    assert rc.expect_passwords[TIMEOUT] is None
    assert EOF in rc.expect_passwords
    assert rc.expect_passwords[EOF] is None


def test_prepare_env_passwords():
    rc = BaseConfig(private_data_dir='/tmp')

    value = {'^SSH [pP]assword.*$': 'secret'}
    password_side_effect = partial(load_file_side_effect, 'env/passwords', value)

    with patch.object(rc.loader, 'load_file', side_effect=password_side_effect):
        rc._prepare_env()
        rc.expect_passwords.pop(TIMEOUT)
        rc.expect_passwords.pop(EOF)
        assert len(rc.expect_passwords) == 1
        assert isinstance(list(rc.expect_passwords.keys())[0], Pattern)
        assert 'secret' in rc.expect_passwords.values()


def test_prepare_environment_subprocess_defaults():
    rc = BaseConfig(private_data_dir="/tmp")
    rc._prepare_env(runner_mode="subprocess")
    assert rc.subprocess_timeout is None


def test_prepare_environment_subprocess_timeout():
    rc = BaseConfig(private_data_dir="/tmp", timeout=100)
    rc._prepare_env(runner_mode="subprocess")

    assert rc.subprocess_timeout == 100


def test_prepare_env_settings_defaults():
    rc = BaseConfig(private_data_dir='/tmp')
    rc._prepare_env()
    assert rc.settings == {}


def test_prepare_env_settings():
    rc = BaseConfig(private_data_dir='/tmp')

    value = {'test': 'string'}
    settings_side_effect = partial(load_file_side_effect, 'env/settings', value)

    with patch.object(rc.loader, 'load_file', side_effect=settings_side_effect):
        rc._prepare_env()
        assert rc.settings == value


def test_prepare_env_sshkey_defaults():
    rc = BaseConfig(private_data_dir='/tmp')
    rc._prepare_env()
    assert rc.ssh_key_data is None


def test_prepare_env_sshkey():
    rc = BaseConfig(private_data_dir='/tmp')

    value = '01234567890'
    sshkey_side_effect = partial(load_file_side_effect, 'env/ssh_key', value)

    with patch.object(rc.loader, 'load_file', side_effect=sshkey_side_effect):
        rc._prepare_env()
        assert rc.ssh_key_data == value


def test_prepare_env_defaults():
    with patch('os.path.exists') as path_exists:
        path_exists.return_value=True
        rc = BaseConfig(private_data_dir='/tmp', host_cwd='/tmp/project')
        rc._prepare_env()
        assert rc.idle_timeout is None
        assert rc.job_timeout is None
        assert rc.pexpect_timeout == 5
        assert rc.host_cwd == '/tmp/project'


@patch.dict('os.environ', {'PYTHONPATH': '/python_path_via_environ',
                           'AWX_LIB_DIRECTORY': '/awx_lib_directory_via_environ'})
def test_prepare_env_ansible_vars():
    rc = BaseConfig(private_data_dir='/tmp')
    rc.ssh_key_data = None
    rc.artifact_dir = '/tmp/artifact'
    rc.env = {}
    rc.execution_mode = BaseExecutionMode.ANSIBLE_COMMANDS

    rc._prepare_env()

    assert not hasattr(rc, 'ssh_key_path')
    assert not hasattr(rc, 'command')

    assert rc.env['ANSIBLE_STDOUT_CALLBACK'] == 'awx_display'
    assert rc.env['ANSIBLE_RETRY_FILES_ENABLED'] == 'False'
    assert rc.env['ANSIBLE_HOST_KEY_CHECKING'] == 'False'
    assert rc.env['AWX_ISOLATED_DATA_DIR'] == '/tmp/artifact'
    assert rc.env['PYTHONPATH'] == '/python_path_via_environ:/awx_lib_directory_via_environ', \
        "PYTHONPATH is the union of the env PYTHONPATH and AWX_LIB_DIRECTORY"

    del rc.env['PYTHONPATH']
    os.environ['PYTHONPATH'] = "/foo/bar/python_path_via_environ"
    rc._prepare_env()
    assert rc.env['PYTHONPATH'] == "/foo/bar/python_path_via_environ:/awx_lib_directory_via_environ", \
        "PYTHONPATH is the union of the explicit env['PYTHONPATH'] override and AWX_LIB_DIRECTORY"


@patch('ansible_runner.config._base.open_fifo_write')
def test_prepare_with_ssh_key(open_fifo_write_mock):
    rc = BaseConfig(private_data_dir='/tmp')
    rc.artifact_dir = '/tmp/artifact'
    rc.env = {}
    rc.execution_mode = BaseExecutionMode.ANSIBLE_COMMANDS
    rc.ssh_key_data = '01234567890'
    rc.command = 'ansible-playbook'
    rc.cmdline_args = []

    with patch.dict('os.environ', {'AWX_LIB_DIRECTORY': '/tmp/artifact'}):
        rc._prepare_env()

    assert rc.ssh_key_path == '/tmp/artifact/ssh_key_data'
    assert open_fifo_write_mock.called


def test_wrap_args_with_ssh_agent_defaults():
    rc = BaseConfig(private_data_dir='/tmp')
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], '/tmp/sshkey')
    assert res == [
        'ssh-agent',
        'sh', '-c',
        "trap 'rm -f /tmp/sshkey' EXIT && ssh-add /tmp/sshkey && rm -f /tmp/sshkey && ansible-playbook main.yaml"
    ]


def test_wrap_args_with_ssh_agent_with_auth():
    rc = BaseConfig(private_data_dir='/tmp')
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], '/tmp/sshkey', '/tmp/sshauth')
    assert res == [
        'ssh-agent', '-a', '/tmp/sshauth',
        'sh', '-c',
        "trap 'rm -f /tmp/sshkey' EXIT && ssh-add /tmp/sshkey && rm -f /tmp/sshkey && ansible-playbook main.yaml"
    ]


def test_wrap_args_with_ssh_agent_silent():
    rc = BaseConfig(private_data_dir='/tmp')
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], '/tmp/sshkey', silence_ssh_add=True)
    assert res == [
        'ssh-agent',
        'sh', '-c',
        "trap 'rm -f /tmp/sshkey' EXIT && ssh-add /tmp/sshkey 2>/dev/null && rm -f /tmp/sshkey && ansible-playbook main.yaml"
    ]


@patch('os.path.isdir', return_value=False)
@patch('os.path.exists', return_value=True)
@patch('os.makedirs', return_value=True)
def test_container_volume_mounting_with_Z(mock_isdir, mock_exists, mock_makedirs, tmpdir):
    rc = BaseConfig(private_data_dir=str(tmpdir))
    os.path.isdir = Mock()
    rc.container_volume_mounts = ['project_path:project_path:Z']
    rc.container_name = 'foo'
    rc.runner_mode = 'pexpect'
    rc.env = {}
    rc.execution_mode = BaseExecutionMode.ANSIBLE_COMMANDS
    rc.command = ['ansible-playbook', 'foo.yml']
    rc.container_image = 'network-ee'
    rc.cmdline_args = ['foo.yml']

    new_args = rc.wrap_args_for_containerization(rc.command, rc.execution_mode, rc.cmdline_args)

    assert new_args[0] == 'podman'
    for i, entry in enumerate(new_args):
        if entry == '-v':
            mount = new_args[i + 1]
            if mount.endswith('project_path:Z'):
                break
    else:
        raise Exception('Could not find expected mount, args: {}'.format(new_args))


@pytest.mark.parametrize('container_runtime', ['docker', 'podman'])
def test_containerization_settings(tmpdir, container_runtime):
    with patch('ansible_runner.config._base.BaseConfig.containerized', new_callable=PropertyMock) as mock_containerized:
        rc = BaseConfig(private_data_dir=tmpdir)
        rc.ident = 'foo'
        rc.cmdline_args = ['main.yaml', '-i', '/tmp/inventory']
        rc.command = ['ansible-playbook'] + rc.cmdline_args
        rc.process_isolation = True
        rc.runner_mode = 'pexpect'
        rc.process_isolation_executable=container_runtime
        rc.container_image = 'my_container'
        rc.container_volume_mounts=['/host1:/container1', 'host2:/container2']
        mock_containerized.return_value = True
        rc.execution_mode = BaseExecutionMode.ANSIBLE_COMMANDS
        rc._prepare_env()
        rc._handle_command_wrap(rc.execution_mode, rc.cmdline_args)

    extra_container_args = []
    if container_runtime == 'podman':
        extra_container_args = ['--quiet']
    else:
        extra_container_args = ['--user={os.getuid()}']

    expected_command_start = [container_runtime, 'run', '--rm', '--tty', '--interactive', '--workdir', '/runner/project'] + \
                             ['-v', '{}/.ssh/:/home/runner/.ssh/'.format(os.environ['HOME'])]
    if container_runtime == 'podman':
        expected_command_start +=['--group-add=root', '--userns=keep-id', '--ipc=host']

    expected_command_start += ['-v', '{}/artifacts/:/runner/artifacts:Z'.format(rc.private_data_dir)] + \
        ['-v', '{}/:/runner:Z'.format(rc.private_data_dir)] + \
        ['--env-file', '{}/env.list'.format(rc.artifact_dir)] + \
        extra_container_args + \
        ['--name', 'ansible_runner_foo'] + \
        ['my_container', 'ansible-playbook', 'main.yaml', '-i', '/tmp/inventory']

    for index, element in enumerate(expected_command_start):
        if '--user=' in element:
            assert '--user=' in rc.command[index]
        else:
            assert rc.command[index] == element
