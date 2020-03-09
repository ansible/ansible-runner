# -*- coding: utf-8 -*-

from functools import partial
from io import StringIO
import os
import re

import six
from pexpect import TIMEOUT, EOF

import pytest
from mock import patch
from mock import Mock

from ansible_runner.runner_config import RunnerConfig, ExecutionMode
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


def test_runner_config_init_defaults():
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


def test_runner_config_with_artifact_dir():
    rc = RunnerConfig('/', artifact_dir='/this-is-some-dir')
    assert rc.artifact_dir == os.path.join('/this-is-some-dir', rc.ident)


def test_runner_config_init_with_ident():
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


def test_runner_config_project_dir():
    rc = RunnerConfig('/', project_dir='/another/path')
    assert rc.project_dir == '/another/path'
    rc = RunnerConfig('/')
    assert rc.project_dir == '/project'


def test_prepare_environment_vars_only_strings():
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


def test_prepare_env_ad_hoc_command():
    rc = RunnerConfig(private_data_dir="/")

    value = {'AD_HOC_COMMAND_ID': 'teststring'}
    envvar_side_effect = partial(load_file_side_effect, 'env/envvars', value)

    with patch.object(rc.loader, 'load_file', side_effect=envvar_side_effect):
        rc.prepare_env()
        assert rc.cwd == '/'


def test_prepare_environment_pexpect_defaults():
    rc = RunnerConfig(private_data_dir="/")
    rc.prepare_env()

    assert len(rc.expect_passwords) == 2
    assert TIMEOUT in rc.expect_passwords
    assert rc.expect_passwords[TIMEOUT] is None
    assert EOF in rc.expect_passwords
    assert rc.expect_passwords[EOF] is None


def test_prepare_env_passwords():
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


def test_prepare_env_extra_vars_defaults():
    rc = RunnerConfig('/')
    rc.prepare_env()
    assert rc.extra_vars is None


def test_prepare_env_settings_defaults():
    rc = RunnerConfig('/')
    rc.prepare_env()
    assert rc.settings == {}


def test_prepare_env_settings():
    rc = RunnerConfig('/')

    value = {'test': 'string'}
    settings_side_effect = partial(load_file_side_effect, 'env/settings', value)

    with patch.object(rc.loader, 'load_file', side_effect=settings_side_effect):
        rc.prepare_env()
        assert rc.settings == value


def test_prepare_env_sshkey_defaults():
    rc = RunnerConfig('/')
    rc.prepare_env()
    assert rc.ssh_key_data is None


def test_prepare_env_sshkey():
    rc = RunnerConfig('/')

    value = '01234567890'
    sshkey_side_effect = partial(load_file_side_effect, 'env/ssh_key', value)

    with patch.object(rc.loader, 'load_file', side_effect=sshkey_side_effect):
        rc.prepare_env()
        assert rc.ssh_key_data == value


def test_prepare_env_defaults():
    with patch('os.path.exists') as path_exists:
        path_exists.return_value=True
        rc = RunnerConfig('/')
        rc.prepare_env()
        assert rc.idle_timeout is None
        assert rc.job_timeout is None
        assert rc.pexpect_timeout == 5
        assert rc.cwd == '/project'


def test_prepare_env_directory_isolation():
    with patch('os.path.exists') as path_exists:
        path_exists.return_value=True
        rc = RunnerConfig('/')
        rc.directory_isolation_path = '/tmp/foo'
        rc.prepare_env()
        assert rc.cwd == '/tmp/foo'


@patch('os.path.exists', return_value=True)
def test_prepare_inventory(path_exists):
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


def test_generate_ansible_command():
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


def test_generate_ansible_command_with_api_extravars():
    rc = RunnerConfig(private_data_dir='/', playbook='main.yaml', extravars={"foo":"bar"})
    with patch('os.path.exists') as path_exists:
        path_exists.return_value=True
        rc.prepare_inventory()

    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', '-e', '{"foo":"bar"}', 'main.yaml']


@pytest.mark.parametrize('cmdline,tokens', [
    (u'--tags foo --skip-tags', ['--tags', 'foo', '--skip-tags']),
    (u'--limit "䉪ቒ칸ⱷ?噂폄蔆㪗輥"', ['--limit', '䉪ቒ칸ⱷ?噂폄蔆㪗輥']),
])
def test_generate_ansible_command_with_cmdline_args(cmdline, tokens):
    rc = RunnerConfig(private_data_dir='/', playbook='main.yaml')
    with patch('os.path.exists') as path_exists:
        path_exists.return_value = True
        rc.prepare_inventory()
    rc.extra_vars = {}

    cmdline_side_effect = partial(load_file_side_effect, 'env/cmdline', cmdline)
    with patch.object(rc.loader, 'load_file', side_effect=cmdline_side_effect):
        cmd = rc.generate_ansible_command()
        assert cmd == ['ansible-playbook'] + tokens + ['-i', '/inventory', 'main.yaml']


def test_prepare_command_defaults():
    rc = RunnerConfig('/')

    cmd_side_effect = partial(load_file_side_effect, 'args')

    def generate_side_effect():
        return StringIO(u'test "string with spaces"')

    with patch.object(rc.loader, 'load_file', side_effect=cmd_side_effect):
        with patch.object(rc, 'generate_ansible_command', side_effect=generate_side_effect):
            rc.prepare_command()
            rc.command == ['test', '"string with spaces"']


def test_prepare_with_defaults():
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


def test_prepare():
    rc = RunnerConfig('/')

    rc.prepare_inventory = Mock()
    rc.prepare_env = Mock()
    rc.prepare_command = Mock()

    rc.ssh_key_data = None
    rc.artifact_dir = '/'
    rc.env = {}
    rc.execution_mode = ExecutionMode.ANSIBLE_PLAYBOOK
    rc.playbook = 'main.yaml'

    os.environ['PYTHONPATH'] = '/python_path_via_environ'
    os.environ['AWX_LIB_DIRECTORY'] = '/awx_lib_directory_via_environ'

    rc.prepare()

    assert rc.prepare_inventory.called
    assert rc.prepare_env.called
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


@patch('ansible_runner.runner_config.open_fifo_write')
def test_prepare_with_ssh_key(open_fifo_write_mock):
    rc = RunnerConfig('/')

    rc.prepare_inventory = Mock()
    rc.prepare_env = Mock()
    rc.prepare_command = Mock()

    rc.wrap_args_with_ssh_agent = Mock()

    rc.ssh_key_data = None
    rc.artifact_dir = '/'
    rc.env = {}
    rc.execution_mode = ExecutionMode.ANSIBLE_PLAYBOOK
    rc.playbook = 'main.yaml'
    rc.ssh_key_data = '01234567890'
    rc.command = 'ansible-playbook'

    os.environ['AWX_LIB_DIRECTORY'] = '/'

    rc.prepare()

    assert rc.ssh_key_path == '/ssh_key_data'
    assert rc.wrap_args_with_ssh_agent.called
    assert open_fifo_write_mock.called


def test_wrap_args_with_ssh_agent_defaults():
    rc = RunnerConfig('/')
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], '/tmp/sshkey')
    assert res == ['ssh-agent', 'sh', '-c', 'ssh-add /tmp/sshkey && rm -f /tmp/sshkey && ansible-playbook main.yaml']


def test_wrap_args_with_ssh_agent_with_auth():
    rc = RunnerConfig('/')
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], '/tmp/sshkey', '/tmp/sshauth')
    assert res == ['ssh-agent', '-a', '/tmp/sshauth', 'sh', '-c', 'ssh-add /tmp/sshkey && rm -f /tmp/sshkey && ansible-playbook main.yaml']


def test_wrap_args_with_ssh_agent_silent():
    rc = RunnerConfig('/')
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], '/tmp/sshkey', silence_ssh_add=True)
    assert res == ['ssh-agent', 'sh', '-c', 'ssh-add /tmp/sshkey 2>/dev/null && rm -f /tmp/sshkey && ansible-playbook main.yaml']


def test_process_isolation_defaults():
    rc = RunnerConfig('/')
    rc.artifact_dir = '/tmp/artifacts'
    rc.playbook = 'main.yaml'
    rc.command = 'ansible-playbook'
    rc.process_isolation = True
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
def test_process_isolation_and_directory_isolation(mock_makedirs, mock_copytree, mock_mkdtemp,
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


def test_process_isolation_settings():
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
    assert rc.command[10] == '/home'

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
