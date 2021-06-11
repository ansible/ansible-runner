# -*- coding: utf-8 -*-

from functools import partial
from io import StringIO
import os
import re

import six
from pexpect import TIMEOUT, EOF

import pytest
from unittest.mock import (Mock, patch, PropertyMock)

from ansible_runner.config.runner import RunnerConfig, ExecutionMode
from ansible_runner.interface import init_runner
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


@patch('os.makedirs', return_value=True)
def test_runner_config_init_defaults(mock_makedirs):
    rc = RunnerConfig('/')
    assert rc.private_data_dir == '/'
    assert rc.ident is not None
    assert rc.playbook is None
    assert rc.inventory is None
    assert rc.limit is None
    assert rc.module is None
    assert rc.module_args is None
    assert rc.artifact_dir == os.path.join('/artifacts/%s' % rc.ident)
    assert isinstance(rc.loader, ArtifactLoader)


@patch('os.makedirs', return_value=True)
def test_runner_config_with_artifact_dir(mock_makedirs):
    rc = RunnerConfig('/', artifact_dir='/this-is-some-dir')
    assert rc.artifact_dir == os.path.join('/this-is-some-dir', rc.ident)


@patch('os.makedirs', return_value=True)
def test_runner_config_init_with_ident(mock_makedirs):
    rc = RunnerConfig('/', ident='test')
    assert rc.private_data_dir == '/'
    assert rc.ident == 'test'
    assert rc.playbook is None
    assert rc.inventory is None
    assert rc.limit is None
    assert rc.module is None
    assert rc.module_args is None
    assert rc.artifact_dir == os.path.join('/artifacts/test')
    assert isinstance(rc.loader, ArtifactLoader)


@patch('os.makedirs', return_value=True)
def test_runner_config_project_dir(mock_makedirs):
    rc = RunnerConfig('/', project_dir='/another/path')
    assert rc.project_dir == '/another/path'
    rc = RunnerConfig('/')
    assert rc.project_dir == '/project'


@patch('os.makedirs', return_value=True)
def test_prepare_environment_vars_only_strings(mock_makedirs):
    rc = RunnerConfig(private_data_dir="/", envvars=dict(D='D'))

    value = dict(A=1, B=True, C="foo")
    envvar_side_effect = partial(load_file_side_effect, 'env/envvars', value)

    with patch.object(rc.loader, 'load_file', side_effect=envvar_side_effect):
        rc.prepare_env()
        assert 'A' in rc.env
        assert isinstance(rc.env['A'], six.string_types)
        assert 'B' in rc.env
        assert isinstance(rc.env['B'], six.string_types)
        assert 'C' in rc.env
        assert isinstance(rc.env['C'], six.string_types)
        assert 'D' in rc.env
        assert rc.env['D'] == 'D'


@patch('os.makedirs', return_value=True)
def test_prepare_env_ad_hoc_command(mock_makedirs):
    rc = RunnerConfig(private_data_dir="/")

    value = {'AD_HOC_COMMAND_ID': 'teststring'}
    envvar_side_effect = partial(load_file_side_effect, 'env/envvars', value)

    with patch.object(rc.loader, 'load_file', side_effect=envvar_side_effect):
        rc.prepare_env()
        assert rc.cwd == '/'


@patch('os.makedirs', return_value=True)
def test_prepare_environment_pexpect_defaults(mock_makedirs):
    rc = RunnerConfig(private_data_dir="/")
    rc.prepare_env()

    assert len(rc.expect_passwords) == 2
    assert TIMEOUT in rc.expect_passwords
    assert rc.expect_passwords[TIMEOUT] is None
    assert EOF in rc.expect_passwords
    assert rc.expect_passwords[EOF] is None


@patch('os.makedirs', return_value=True)
def test_prepare_env_passwords(mock_makedirs):
    rc = RunnerConfig(private_data_dir='/')

    value = {'^SSH [pP]assword.*$': 'secret'}
    password_side_effect = partial(load_file_side_effect, 'env/passwords', value)

    with patch.object(rc.loader, 'load_file', side_effect=password_side_effect):
        rc.prepare_env()
        rc.expect_passwords.pop(TIMEOUT)
        rc.expect_passwords.pop(EOF)
        assert len(rc.expect_passwords) == 1
        assert isinstance(list(rc.expect_passwords.keys())[0], Pattern)
        assert 'secret' in rc.expect_passwords.values()


@patch('os.makedirs', return_value=True)
def test_prepare_env_extra_vars_defaults(mock_makedirs):
    rc = RunnerConfig('/')
    rc.prepare_env()
    assert rc.extra_vars is None


@patch('os.makedirs', return_value=True)
def test_prepare_env_settings_defaults(mock_makedirs):
    rc = RunnerConfig('/')
    rc.prepare_env()
    assert rc.settings == {}


@patch('os.makedirs', return_value=True)
def test_prepare_env_settings(mock_makedirs):
    rc = RunnerConfig('/')

    value = {'test': 'string'}
    settings_side_effect = partial(load_file_side_effect, 'env/settings', value)

    with patch.object(rc.loader, 'load_file', side_effect=settings_side_effect):
        rc.prepare_env()
        assert rc.settings == value


@patch('os.makedirs', return_value=True)
def test_prepare_env_sshkey_defaults(mock_makedirs):
    rc = RunnerConfig('/')
    rc.prepare_env()
    assert rc.ssh_key_data is None


@patch('ansible_runner.config._base.open_fifo_write')
@patch('os.makedirs', return_value=True)
def test_prepare_env_sshkey(mock_makedirs, open_fifo_write_mock):
    rc = RunnerConfig('/')

    value = '01234567890'
    sshkey_side_effect = partial(load_file_side_effect, 'env/ssh_key', value)

    with patch.object(rc.loader, 'load_file', side_effect=sshkey_side_effect):
        rc.prepare_env()
        assert rc.ssh_key_data == value


@patch('os.makedirs', return_value=True)
def test_prepare_env_defaults(mock_makedirs):
    with patch('os.path.exists') as path_exists:
        path_exists.return_value=True
        rc = RunnerConfig('/')
        rc.prepare_env()
        assert rc.idle_timeout is None
        assert rc.job_timeout is None
        assert rc.pexpect_timeout == 5
        assert rc.cwd == '/project'


@patch('os.makedirs', return_value=True)
def test_prepare_env_directory_isolation(mock_makedirs):
    with patch('os.path.exists') as path_exists:
        path_exists.return_value=True
        rc = RunnerConfig('/')
        rc.directory_isolation_path = '/tmp/foo'
        rc.prepare_env()
        assert rc.cwd == '/tmp/foo'


@patch('os.makedirs', return_value=True)
@patch('os.path.exists', return_value=True)
def test_prepare_inventory(path_exists, mock_makedirs):
    rc = RunnerConfig(private_data_dir='/')
    rc.prepare_inventory()
    assert rc.inventory == '/inventory'
    rc.inventory = '/tmp/inventory'
    rc.prepare_inventory()
    assert rc.inventory == '/tmp/inventory'
    rc.inventory = 'localhost,anotherhost,'
    rc.prepare_inventory()
    assert rc.inventory == 'localhost,anotherhost,'
    path_exists.return_value = False
    rc.inventory = None
    rc.prepare_inventory()
    assert rc.inventory is None


@patch('os.makedirs', return_value=True)
def test_generate_ansible_command(mock_makedirs):
    rc = RunnerConfig(private_data_dir='/', playbook='main.yaml')
    with patch('os.path.exists') as path_exists:
        path_exists.return_value=True
        rc.prepare_inventory()
    rc.extra_vars = None

    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', 'main.yaml']

    rc.extra_vars = dict(test="key")
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', '-e', '{"test":"key"}', 'main.yaml']

    with patch.object(rc.loader, 'isfile', side_effect=lambda x: True):
        cmd = rc.generate_ansible_command()
        assert cmd == ['ansible-playbook', '-i', '/inventory', '-e', '@/env/extravars', '-e', '{"test":"key"}', 'main.yaml']
        rc.extra_vars = '/tmp/extravars.yml'
        cmd = rc.generate_ansible_command()
        assert cmd == ['ansible-playbook', '-i', '/inventory', '-e', '@/env/extravars', '-e', '@/tmp/extravars.yml', 'main.yaml']
        rc.extra_vars = None
        cmd = rc.generate_ansible_command()
        assert cmd == ['ansible-playbook', '-i', '/inventory', '-e', '@/env/extravars', 'main.yaml']
    rc.extra_vars = None

    rc.inventory = "localhost,"
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', 'localhost,', 'main.yaml']

    rc.inventory = ['thing1', 'thing2']
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', 'thing1', '-i', 'thing2', 'main.yaml']

    rc.inventory = []
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', 'main.yaml']
    rc.inventory = None

    with patch('os.path.exists', return_value=False) as path_exists:
        rc.prepare_inventory()
        cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', 'main.yaml']

    rc.verbosity = 3
    with patch('os.path.exists', return_value=True) as path_exists:
        rc.prepare_inventory()
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', '-vvv', 'main.yaml']
    rc.verbosity = None

    rc.limit = 'hosts'
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', '--limit', 'hosts', 'main.yaml']
    rc.limit = None

    rc.module = 'setup'
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible', '-i', '/inventory', '-m', 'setup']
    rc.module = None

    rc.module = 'setup'
    rc.module_args = 'test=string'
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible', '-i', '/inventory', '-m', 'setup', '-a', 'test=string']
    rc.module_args = None
    rc.module = None

    rc.forks = 5
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', '--forks', '5', 'main.yaml']


@patch('os.makedirs', return_value=True)
def test_generate_ansible_command_with_api_extravars(mock_makedirs):
    rc = RunnerConfig(private_data_dir='/', playbook='main.yaml', extravars={"foo":"bar"})
    with patch('os.path.exists') as path_exists:
        path_exists.return_value=True
        rc.prepare_inventory()

    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', '-e', '{"foo":"bar"}', 'main.yaml']


@patch('os.makedirs', return_value=True)
def test_generate_ansible_command_with_dict_extravars(mock_makedirs):
    rc = RunnerConfig(private_data_dir='/', playbook='main.yaml', extravars={"foo":"test \n hello"})
    with patch('os.path.exists') as path_exists:
        path_exists.return_value=True
        rc.prepare_inventory()

    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', '-e', '{"foo":"test \\n hello"}', 'main.yaml']


@pytest.mark.parametrize('cmdline,tokens', [
    (u'--tags foo --skip-tags', ['--tags', 'foo', '--skip-tags']),
    (u'--limit "䉪ቒ칸ⱷ?噂폄蔆㪗輥"', ['--limit', '䉪ቒ칸ⱷ?噂폄蔆㪗輥']),
])
@patch('os.makedirs', return_value=True)
def test_generate_ansible_command_with_cmdline_args(mock_makedirs, cmdline, tokens):
    rc = RunnerConfig(private_data_dir='/', playbook='main.yaml')
    with patch('os.path.exists') as path_exists:
        path_exists.return_value = True
        rc.prepare_inventory()
    rc.extra_vars = {}

    cmdline_side_effect = partial(load_file_side_effect, 'env/cmdline', cmdline)
    with patch.object(rc.loader, 'load_file', side_effect=cmdline_side_effect):
        cmd = rc.generate_ansible_command()
        assert cmd == ['ansible-playbook'] + tokens + ['-i', '/inventory', 'main.yaml']


@patch('os.makedirs', return_value=True)
def test_prepare_command_defaults(mock_makedirs):
    rc = RunnerConfig('/')

    cmd_side_effect = partial(load_file_side_effect, 'args')

    def generate_side_effect():
        return StringIO(u'test "string with spaces"')

    with patch.object(rc.loader, 'load_file', side_effect=cmd_side_effect):
        with patch.object(rc, 'generate_ansible_command', side_effect=generate_side_effect):
            rc.prepare_command()
            rc.command == ['test', '"string with spaces"']


@patch('os.makedirs', return_value=True)
def test_prepare_with_defaults(mock_makedirs):
    rc = RunnerConfig('/')

    rc.prepare_inventory = Mock()
    rc.prepare_env = Mock()
    rc.prepare_command = Mock()

    rc.ssh_key_data = None
    rc.artifact_dir = '/'
    rc.env = {}

    with pytest.raises(ConfigurationError) as exc:
        rc.prepare()

    assert str(exc.value) == 'No executable for runner to run'


@patch.dict('os.environ', {'PYTHONPATH': '/python_path_via_environ',
                           'AWX_LIB_DIRECTORY': '/awx_lib_directory_via_environ'})
@patch('os.makedirs', return_value=True)
def test_prepare(mock_makedirs):
    rc = RunnerConfig('/')

    rc.prepare_inventory = Mock()
    rc.prepare_command = Mock()

    rc.ssh_key_data = None
    rc.artifact_dir = '/'
    rc.env = {}
    rc.execution_mode = ExecutionMode.ANSIBLE_PLAYBOOK
    rc.playbook = 'main.yaml'

    rc.prepare()

    assert rc.prepare_inventory.called
    assert rc.prepare_command.called

    assert not hasattr(rc, 'ssh_key_path')
    assert not hasattr(rc, 'command')

    assert rc.env['ANSIBLE_STDOUT_CALLBACK'] == 'awx_display'
    assert rc.env['ANSIBLE_RETRY_FILES_ENABLED'] == 'False'
    assert rc.env['ANSIBLE_HOST_KEY_CHECKING'] == 'False'
    assert rc.env['AWX_ISOLATED_DATA_DIR'] == '/'
    assert rc.env['PYTHONPATH'] == '/python_path_via_environ:/awx_lib_directory_via_environ', \
        "PYTHONPATH is the union of the env PYTHONPATH and AWX_LIB_DIRECTORY"

    del rc.env['PYTHONPATH']
    os.environ['PYTHONPATH'] = "/foo/bar/python_path_via_environ"
    rc.prepare()
    assert rc.env['PYTHONPATH'] == "/foo/bar/python_path_via_environ:/awx_lib_directory_via_environ", \
        "PYTHONPATH is the union of the explicit env['PYTHONPATH'] override and AWX_LIB_DIRECTORY"


@patch('os.makedirs', return_value=True)
@patch('ansible_runner.config._base.open_fifo_write')
def test_prepare_with_ssh_key(open_fifo_write_mock, mock_makedirs):
    rc = RunnerConfig('/')

    rc.prepare_inventory = Mock()
    rc.prepare_command = Mock()

    rc.wrap_args_with_ssh_agent = Mock()

    rc.ssh_key_data = None
    rc.artifact_dir = '/'
    rc.env = {}
    rc.execution_mode = ExecutionMode.ANSIBLE_PLAYBOOK
    rc.playbook = 'main.yaml'
    rc.ssh_key_data = '01234567890'
    rc.command = 'ansible-playbook'

    with patch.dict('os.environ', {'AWX_LIB_DIRECTORY': '/'}):
        rc.prepare()

    assert rc.ssh_key_path == '/ssh_key_data'
    assert rc.wrap_args_with_ssh_agent.called
    assert open_fifo_write_mock.called


@patch('os.makedirs', return_value=True)
def test_wrap_args_with_ssh_agent_defaults(mock_makedirs):
    rc = RunnerConfig('/')
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], '/tmp/sshkey')
    assert res == [
        'ssh-agent',
        'sh', '-c',
        "trap 'rm -f /tmp/sshkey' EXIT && ssh-add /tmp/sshkey && rm -f /tmp/sshkey && ansible-playbook main.yaml"
    ]


@patch('os.makedirs', return_value=True)
def test_wrap_args_with_ssh_agent_with_auth(mock_makedirs):
    rc = RunnerConfig('/')
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], '/tmp/sshkey', '/tmp/sshauth')
    assert res == [
        'ssh-agent', '-a', '/tmp/sshauth',
        'sh', '-c',
        "trap 'rm -f /tmp/sshkey' EXIT && ssh-add /tmp/sshkey && rm -f /tmp/sshkey && ansible-playbook main.yaml"
    ]


@patch('os.makedirs', return_value=True)
def test_wrap_args_with_ssh_agent_silent(mock_makedirs):
    rc = RunnerConfig('/')
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], '/tmp/sshkey', silence_ssh_add=True)
    assert res == [
        'ssh-agent',
        'sh', '-c',
        "trap 'rm -f /tmp/sshkey' EXIT && ssh-add /tmp/sshkey 2>/dev/null && rm -f /tmp/sshkey && ansible-playbook main.yaml"
    ]


@patch('ansible_runner.runner_config.RunnerConfig.prepare')
@patch('ansible_runner.interface.sys')
@patch('ansible_runner.utils.subprocess')
@pytest.mark.parametrize('executable_present', [True, False])
def test_process_isolation_executable_not_found(mock_subprocess, mock_sys, mock_prepare, executable_present):
    # Mock subprocess.Popen indicates if
    # process isolation executable is present
    mock_proc = Mock()
    mock_proc.returncode=(0 if executable_present else 1)
    mock_subprocess.Popen.return_value = mock_proc

    kwargs = {'process_isolation': True,
              'process_isolation_executable': 'fake_executable'}
    init_runner(**kwargs)
    if executable_present:
        assert not mock_sys.exit.called
    else:
        assert mock_sys.exit.called


@patch('os.makedirs', return_value=True)
def test_bwrap_process_isolation_defaults(mock_makedirs):
    rc = RunnerConfig('/')
    rc.artifact_dir = '/tmp/artifacts'
    rc.playbook = 'main.yaml'
    rc.command = 'ansible-playbook'
    rc.process_isolation = True
    rc.process_isolation_executable = 'bwrap'
    with patch('os.path.exists') as path_exists:
        path_exists.return_value=True
        rc.prepare()

    assert rc.command == [
        'bwrap',
        '--die-with-parent',
        '--unshare-pid',
        '--dev-bind', '/', '/',
        '--proc', '/proc',
        '--bind', '/', '/',
        '--chdir', '/project',
        'ansible-playbook', '-i', '/inventory', 'main.yaml',
    ]


@patch('os.makedirs', return_value=True)
@patch('shutil.copytree', return_value=True)
@patch('tempfile.mkdtemp', return_value="/tmp/dirisolation/foo")
@patch('os.chmod', return_value=True)
@patch('shutil.rmtree', return_value=True)
def test_bwrap_process_isolation_and_directory_isolation(mock_makedirs, mock_copytree, mock_mkdtemp,
                                                         mock_chmod, mock_rmtree):
    def new_exists(path):
        if path == "/project":
            return False
        return True
    rc = RunnerConfig('/')
    rc.artifact_dir = '/tmp/artifacts'
    rc.directory_isolation_path = '/tmp/dirisolation'
    rc.playbook = 'main.yaml'
    rc.command = 'ansible-playbook'
    rc.process_isolation = True
    rc.process_isolation_executable = 'bwrap'
    with patch('os.path.exists', new=new_exists):
        rc.prepare()

    assert rc.command == [
        'bwrap',
        '--die-with-parent',
        '--unshare-pid',
        '--dev-bind', '/', '/',
        '--proc', '/proc',
        '--bind', '/', '/',
        '--chdir', os.path.realpath(rc.directory_isolation_path),
        'ansible-playbook', '-i', '/inventory', 'main.yaml',
    ]


@patch('os.path.isdir', return_value=False)
@patch('os.path.exists', return_value=True)
@patch('os.makedirs', return_value=True)
def test_process_isolation_settings(mock_isdir, mock_exists, mock_makedirs):
    rc = RunnerConfig('/')
    rc.artifact_dir = '/tmp/artifacts'
    rc.playbook = 'main.yaml'
    rc.command = 'ansible-playbook'
    rc.process_isolation = True
    rc.process_isolation_executable = 'not_bwrap'
    rc.process_isolation_hide_paths = ['/home', '/var']
    rc.process_isolation_show_paths = ['/usr']
    rc.process_isolation_ro_paths = ['/venv']
    rc.process_isolation_path = '/tmp'

    with patch('os.path.exists') as path_exists:
        path_exists.return_value=True
        rc.prepare()
    print(rc.command)
    assert rc.command[0:8] == [
        'not_bwrap',
        '--die-with-parent',
        '--unshare-pid',
        '--dev-bind', '/', '/',
        '--proc', '/proc',
    ]

    # hide /home
    assert rc.command[8] == '--bind'
    assert 'ansible_runner_pi' in rc.command[9]
    assert rc.command[10] == os.path.realpath('/home')  # needed for Mac

    # hide /var
    assert rc.command[11] == '--bind'
    assert 'ansible_runner_pi' in rc.command[12]
    assert rc.command[13] == '/var' or rc.command[13] == '/private/var'

    # read-only bind
    assert rc.command[14:17] == ['--ro-bind', '/venv', '/venv']

    # root bind
    assert rc.command[17:20] == ['--bind', '/', '/']

    # show /usr
    assert rc.command[20:23] == ['--bind', '/usr', '/usr']

    # chdir and ansible-playbook command
    assert rc.command[23:] == ['--chdir', '/project', 'ansible-playbook', '-i', '/inventory', 'main.yaml']


@patch('os.mkdir', return_value=True)
def test_profiling_plugin_settings(mock_mkdir):
    rc = RunnerConfig('/')
    rc.playbook = 'main.yaml'
    rc.command = 'ansible-playbook'
    rc.resource_profiling = True
    rc.resource_profiling_base_cgroup = 'ansible-runner'
    rc.prepare()

    expected_command_start = [
        'cgexec',
        '--sticky',
        '-g',
        'cpuacct,memory,pids:ansible-runner/{}'.format(rc.ident),
        'ansible-playbook'
    ]
    for index, element in enumerate(expected_command_start):
        assert rc.command[index] == element
    assert 'main.yaml' in rc.command
    assert rc.env['ANSIBLE_CALLBACK_WHITELIST'] == 'cgroup_perf_recap'
    assert rc.env['CGROUP_CONTROL_GROUP'] == 'ansible-runner/{}'.format(rc.ident)
    assert rc.env['CGROUP_OUTPUT_DIR'] == os.path.normpath(os.path.join(rc.private_data_dir, 'profiling_data'))
    assert rc.env['CGROUP_OUTPUT_FORMAT'] == 'json'
    assert rc.env['CGROUP_CPU_POLL_INTERVAL'] == '0.25'
    assert rc.env['CGROUP_MEMORY_POLL_INTERVAL'] == '0.25'
    assert rc.env['CGROUP_PID_POLL_INTERVAL'] == '0.25'
    assert rc.env['CGROUP_FILE_PER_TASK'] == 'True'
    assert rc.env['CGROUP_WRITE_FILES'] == 'True'
    assert rc.env['CGROUP_DISPLAY_RECAP'] == 'False'


@patch('os.mkdir', return_value=True)
def test_profiling_plugin_settings_with_custom_intervals(mock_mkdir):
    rc = RunnerConfig('/')
    rc.playbook = 'main.yaml'
    rc.command = 'ansible-playbook'
    rc.resource_profiling = True
    rc.resource_profiling_base_cgroup = 'ansible-runner'
    rc.resource_profiling_cpu_poll_interval = '.5'
    rc.resource_profiling_memory_poll_interval = '.75'
    rc.resource_profiling_pid_poll_interval = '1.5'
    rc.prepare()
    assert rc.env['CGROUP_CPU_POLL_INTERVAL'] == '.5'
    assert rc.env['CGROUP_MEMORY_POLL_INTERVAL'] == '.75'
    assert rc.env['CGROUP_PID_POLL_INTERVAL'] == '1.5'


@patch('os.path.isdir', return_value=True)
@patch('os.path.exists', return_value=True)
def test_container_volume_mounting_with_Z(mock_isdir, mock_exists, tmpdir):
    rc = RunnerConfig(str(tmpdir))
    rc.container_volume_mounts = ['project_path:project_path:Z']
    rc.container_name = 'foo'
    rc.env = {}
    new_args = rc.wrap_args_for_containerization(['ansible-playbook', 'foo.yml'], 0, None)
    assert new_args[0] == 'podman'
    for i, entry in enumerate(new_args):
        if entry == '-v':
            mount = new_args[i + 1]
            if mount.endswith(':project_path:Z'):
                break
    else:
        raise Exception('Could not find expected mount, args: {}'.format(new_args))


@pytest.mark.parametrize('container_runtime', ['docker', 'podman'])
@patch('os.path.isdir', return_value=True)
@patch('os.path.exists', return_value=True)
def test_containerization_settings(mock_isdir, mock_exists, tmpdir, container_runtime):
    with patch('ansible_runner.runner_config.RunnerConfig.containerized', new_callable=PropertyMock) as mock_containerized:
        rc = RunnerConfig(tmpdir)
        rc.ident = 'foo'
        rc.playbook = 'main.yaml'
        rc.command = 'ansible-playbook'
        rc.process_isolation = True
        rc.process_isolation_executable=container_runtime
        rc.container_image = 'my_container'
        rc.container_volume_mounts=['/host1:/container1', 'host2:/container2']
        mock_containerized.return_value = True
        rc.prepare()

    extra_container_args = []
    if container_runtime == 'podman':
        extra_container_args = ['--quiet']
    else:
        extra_container_args = ['--user={os.getuid()}']

    expected_command_start = [container_runtime, 'run', '--rm', '--tty', '--interactive', '--workdir', '/runner/project'] + \
        ['-v', '{}/:/runner:Z'.format(rc.private_data_dir)] + \
        ['-v', '/host1/:/container1', '-v', 'host2/:/container2'] + \
        ['--env-file', '{}/env.list'.format(rc.artifact_dir)] + \
        extra_container_args + \
        ['--name', 'ansible_runner_foo'] + \
        ['my_container', 'ansible-playbook', '-i', '/runner/inventory/hosts', 'main.yaml']

    for index, element in enumerate(expected_command_start):
        if '--user' in element:
            assert '--user=' in rc.command[index]
        else:
            assert rc.command[index] == element
