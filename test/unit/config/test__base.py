# -*- coding: utf-8 -*-

import os
import re
import six

from functools import partial

import pytest

from pexpect import TIMEOUT, EOF

from ansible_runner.config._base import BaseConfig, BaseExecutionMode
from ansible_runner.loader import ArtifactLoader
from ansible_runner.exceptions import ConfigurationError
from test.utils.common import RSAKey

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


def test_base_config_init_defaults(tmp_path):
    rc = BaseConfig(private_data_dir=tmp_path.as_posix())
    assert rc.private_data_dir == tmp_path.as_posix()
    assert rc.ident is not None
    assert rc.process_isolation is False
    assert rc.fact_cache_type == 'jsonfile'
    assert rc.json_mode is False
    assert rc.quiet is False
    assert rc.quiet is False
    assert rc.rotate_artifacts == 0
    assert rc.artifact_dir == tmp_path.joinpath('artifacts').joinpath(rc.ident).as_posix()
    assert isinstance(rc.loader, ArtifactLoader)


def test_base_config_with_artifact_dir(tmp_path, patch_private_data_dir):
    rc = BaseConfig(artifact_dir=tmp_path.joinpath('this-is-some-dir').as_posix())
    assert rc.artifact_dir == tmp_path.joinpath('this-is-some-dir').joinpath(rc.ident).as_posix()

    # Check that the private data dir is placed in our default location with our default prefix
    # and has some extra uniqueness on the end.
    base_private_data_dir = tmp_path.joinpath('.ansible-runner-').as_posix()
    assert rc.private_data_dir.startswith(base_private_data_dir)
    assert len(rc.private_data_dir) > len(base_private_data_dir)

    rc._prepare_env()
    assert not tmp_path.joinpath('artifacts').exists()
    assert tmp_path.joinpath('this-is-some-dir').exists()


def test_base_config_init_with_ident(tmp_path):
    rc = BaseConfig(private_data_dir=tmp_path.as_posix(), ident='test')
    assert rc.private_data_dir == tmp_path.as_posix()
    assert rc.ident == 'test'
    assert rc.artifact_dir == tmp_path.joinpath('artifacts').joinpath('test').as_posix()
    assert isinstance(rc.loader, ArtifactLoader)


def test_base_config_project_dir(tmp_path):
    rc = BaseConfig(private_data_dir=tmp_path.as_posix(), project_dir='/another/path')
    assert rc.project_dir == '/another/path'
    rc = BaseConfig(private_data_dir=tmp_path.as_posix())
    assert rc.project_dir == tmp_path.joinpath('project').as_posix()


def test_prepare_environment_vars_only_strings_from_file(mocker):
    rc = BaseConfig(envvars=dict(D='D'))

    value = dict(A=1, B=True, C="foo")
    envvar_side_effect = partial(load_file_side_effect, 'env/envvars', value)

    mocker.patch.object(rc.loader, 'load_file', side_effect=envvar_side_effect)

    rc._prepare_env()
    assert 'A' in rc.env
    assert isinstance(rc.env['A'], six.string_types)
    assert 'B' in rc.env
    assert isinstance(rc.env['B'], six.string_types)
    assert 'C' in rc.env
    assert isinstance(rc.env['C'], six.string_types)
    assert 'D' in rc.env
    assert rc.env['D'] == 'D'


def test_prepare_environment_vars_only_strings_from_interface():
    rc = BaseConfig(envvars=dict(D='D', A=1, B=True, C="foo"))
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
    rc = BaseConfig()
    rc._prepare_env()

    assert len(rc.expect_passwords) == 2
    assert TIMEOUT in rc.expect_passwords
    assert rc.expect_passwords[TIMEOUT] is None
    assert EOF in rc.expect_passwords
    assert rc.expect_passwords[EOF] is None


def test_prepare_env_passwords(mocker):
    rc = BaseConfig()

    value = {'^SSH [pP]assword.*$': 'secret'}
    password_side_effect = partial(load_file_side_effect, 'env/passwords', value)

    mocker.patch.object(rc.loader, 'load_file', side_effect=password_side_effect)
    rc._prepare_env()
    rc.expect_passwords.pop(TIMEOUT)
    rc.expect_passwords.pop(EOF)
    assert len(rc.expect_passwords) == 1
    assert isinstance(list(rc.expect_passwords.keys())[0], Pattern)
    assert 'secret' in rc.expect_passwords.values()


def test_prepare_environment_subprocess_defaults():
    rc = BaseConfig()
    rc._prepare_env(runner_mode="subprocess")
    assert rc.subprocess_timeout is None


def test_prepare_environment_subprocess_timeout():
    rc = BaseConfig(timeout=100)
    rc._prepare_env(runner_mode="subprocess")

    assert rc.subprocess_timeout == 100


def test_prepare_env_settings_defaults():
    rc = BaseConfig()
    rc._prepare_env()
    assert rc.settings == {}


def test_prepare_env_settings(mocker):
    rc = BaseConfig()

    value = {'test': 'string'}
    settings_side_effect = partial(load_file_side_effect, 'env/settings', value)

    mocker.patch.object(rc.loader, 'load_file', side_effect=settings_side_effect)
    rc._prepare_env()
    assert rc.settings == value


def test_prepare_env_sshkey_defaults():
    rc = BaseConfig()
    rc._prepare_env()
    assert rc.ssh_key_data is None


def test_prepare_env_sshkey(mocker):
    rc = BaseConfig()

    rsa_key = RSAKey()
    rsa_private_key_value = rsa_key.private
    sshkey_side_effect = partial(load_file_side_effect, 'env/ssh_key', rsa_private_key_value)

    mocker.patch.object(rc.loader, 'load_file', side_effect=sshkey_side_effect)
    rc._prepare_env()
    assert rc.ssh_key_data == rsa_private_key_value


def test_prepare_env_defaults():
    rc = BaseConfig(host_cwd='/tmp/project')
    rc._prepare_env()

    assert rc.idle_timeout is None
    assert rc.job_timeout is None
    assert rc.pexpect_timeout == 5
    assert rc.host_cwd == '/tmp/project'


def test_prepare_env_ansible_vars(mocker, tmp_path):
    mocker.patch.dict('os.environ', {
        'AWX_LIB_DIRECTORY': '/awx_lib_directory_via_environ',
    })

    artifact_dir = tmp_path.joinpath('some_artifacts')
    rc = BaseConfig(artifact_dir=artifact_dir.as_posix())
    rc.ssh_key_data = None
    rc.env = {}
    rc.execution_mode = BaseExecutionMode.ANSIBLE_COMMANDS

    rc._prepare_env()

    assert not hasattr(rc, 'ssh_key_path')
    assert not hasattr(rc, 'command')

    assert rc.env['ANSIBLE_STDOUT_CALLBACK'] == 'awx_display'
    assert rc.env['ANSIBLE_RETRY_FILES_ENABLED'] == 'False'
    assert rc.env['ANSIBLE_HOST_KEY_CHECKING'] == 'False'
    assert rc.env['AWX_ISOLATED_DATA_DIR'] == artifact_dir.joinpath(rc.ident).as_posix()


def test_prepare_with_ssh_key(mocker, tmp_path):
    open_fifo_write_mock = mocker.patch('ansible_runner.config._base.open_fifo_write')
    custom_artifacts = tmp_path.joinpath('custom_arts')

    rc = BaseConfig(private_data_dir=tmp_path.as_posix(), artifact_dir=custom_artifacts.as_posix())
    rc.artifact_dir = custom_artifacts.as_posix()
    rc.env = {}
    rc.execution_mode = BaseExecutionMode.ANSIBLE_COMMANDS
    rsa_key = RSAKey()
    rc.ssh_key_data = rsa_key.private
    rc.command = 'ansible-playbook'
    rc.cmdline_args = []
    rc._prepare_env()

    assert rc.ssh_key_path == custom_artifacts.joinpath('ssh_key_data').as_posix()
    assert open_fifo_write_mock.called


def test_wrap_args_with_ssh_agent_defaults(tmp_path):
    rc = BaseConfig(private_data_dir=str(tmp_path))
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], f'{tmp_path}/sshkey')
    assert res == [
        'ssh-agent',
        'sh', '-c',
        f"trap 'rm -f {tmp_path}/sshkey' EXIT && ssh-add {tmp_path}/sshkey && rm -f {tmp_path}/sshkey && ansible-playbook main.yaml"
    ]


def test_wrap_args_with_ssh_agent_with_auth(tmp_path):
    rc = BaseConfig(private_data_dir=str(tmp_path))
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], f'{tmp_path}/sshkey', f'{tmp_path}/sshauth')
    assert res == [
        'ssh-agent', '-a', f'{tmp_path}/sshauth',
        'sh', '-c',
        f"trap 'rm -f {tmp_path}/sshkey' EXIT && ssh-add {tmp_path}/sshkey && rm -f {tmp_path}/sshkey && ansible-playbook main.yaml"
    ]


def test_wrap_args_with_ssh_agent_silent(tmp_path):
    rc = BaseConfig(private_data_dir=str(tmp_path))
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], f'{tmp_path}/sshkey', silence_ssh_add=True)
    assert res == [
        'ssh-agent',
        'sh', '-c',
        f"trap 'rm -f {tmp_path}/sshkey' EXIT && ssh-add {tmp_path}/sshkey 2>/dev/null && rm -f {tmp_path}/sshkey && ansible-playbook main.yaml"
    ]


def test_container_volume_mounting_with_Z(tmp_path, mocker):
    mocker.patch('os.path.isdir', return_value=False)
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('os.makedirs', return_value=True)

    rc = BaseConfig(private_data_dir=str(tmp_path))
    os.path.isdir = mocker.Mock()
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
            if mount.endswith('project_path/:Z'):
                break
    else:
        raise Exception('Could not find expected mount, args: {}'.format(new_args))


@pytest.mark.parametrize('runtime', ('docker', 'podman'))
def test_containerization_settings(tmp_path, runtime, mocker):
    mocker.patch.dict('os.environ', {'HOME': str(tmp_path)}, clear=True)
    tmp_path.joinpath('.ssh').mkdir()

    mock_containerized = mocker.patch('ansible_runner.config._base.BaseConfig.containerized', new_callable=mocker.PropertyMock)
    mock_containerized.return_value = True

    rc = BaseConfig(private_data_dir=tmp_path)
    rc.ident = 'foo'
    rc.cmdline_args = ['main.yaml', '-i', '/tmp/inventory']
    rc.command = ['ansible-playbook'] + rc.cmdline_args
    rc.process_isolation = True
    rc.runner_mode = 'pexpect'
    rc.process_isolation_executable = runtime
    rc.container_image = 'my_container'
    rc.container_volume_mounts = ['/host1:/container1', 'host2:/container2']
    rc.execution_mode = BaseExecutionMode.ANSIBLE_COMMANDS
    rc._prepare_env()
    rc._handle_command_wrap(rc.execution_mode, rc.cmdline_args)

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
        '-v', '{}/.ssh/:/home/runner/.ssh/'.format(str(tmp_path)),
        '-v', '{}/.ssh/:/root/.ssh/'.format(str(tmp_path)),
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
        'my_container', 'ansible-playbook', 'main.yaml', '-i', '/tmp/inventory',
    ])

    assert expected_command_start == rc.command


@pytest.mark.parametrize('runtime', ('docker', 'podman'))
def test_containerization_unsafe_write_setting(tmp_path, runtime, mocker):
    mock_containerized = mocker.patch('ansible_runner.config._base.BaseConfig.containerized', new_callable=mocker.PropertyMock)

    rc = BaseConfig(private_data_dir=tmp_path)
    rc.ident = 'foo'
    rc.cmdline_args = ['main.yaml', '-i', '/tmp/inventory']
    rc.command = ['ansible-playbook'] + rc.cmdline_args
    rc.process_isolation = True
    rc.runner_mode = 'pexpect'
    rc.process_isolation_executable = runtime
    rc.container_image = 'my_container'
    rc.container_volume_mounts = ['/host1:/container1', 'host2:/container2']
    mock_containerized.return_value = True
    rc.execution_mode = BaseExecutionMode.ANSIBLE_COMMANDS
    rc._prepare_env()
    rc._handle_command_wrap(rc.execution_mode, rc.cmdline_args)

    expected = {
        'docker': None,
        'podman': '1',
    }

    assert rc.env.get('ANSIBLE_UNSAFE_WRITES') == expected[runtime]
