# -*- coding: utf-8 -*-

from functools import partial
from io import StringIO
import os
import re
import six

from pexpect import TIMEOUT, EOF

import pytest

from ansible_runner.config.runner import RunnerConfig, ExecutionMode
from ansible_runner.interface import init_runner
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


def test_runner_config_init_defaults(mocker):
    mocker.patch('os.makedirs', return_value=True)

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


def test_runner_config_with_artifact_dir(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig('/', artifact_dir='/this-is-some-dir')
    assert rc.artifact_dir == os.path.join('/this-is-some-dir', rc.ident)


def test_runner_config_init_with_ident(mocker):
    mocker.patch('os.makedirs', return_value=True)

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


def test_runner_config_project_dir(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig('/', project_dir='/another/path')
    assert rc.project_dir == '/another/path'
    rc = RunnerConfig('/')
    assert rc.project_dir == '/project'


def test_prepare_environment_vars_only_strings(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig(private_data_dir="/", envvars=dict(D='D'))

    value = dict(A=1, B=True, C="foo")
    envvar_side_effect = partial(load_file_side_effect, 'env/envvars', value)

    mocker.patch.object(rc.loader, 'load_file', side_effect=envvar_side_effect)

    rc.prepare_env()
    assert 'A' in rc.env
    assert isinstance(rc.env['A'], six.string_types)
    assert 'B' in rc.env
    assert isinstance(rc.env['B'], six.string_types)
    assert 'C' in rc.env
    assert isinstance(rc.env['C'], six.string_types)
    assert 'D' in rc.env
    assert rc.env['D'] == 'D'


def test_prepare_env_ad_hoc_command(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig(private_data_dir="/")

    value = {'AD_HOC_COMMAND_ID': 'teststring'}
    envvar_side_effect = partial(load_file_side_effect, 'env/envvars', value)

    mocker.patch.object(rc.loader, 'load_file', side_effect=envvar_side_effect)

    rc.prepare_env()
    assert rc.cwd == '/'


def test_prepare_environment_pexpect_defaults(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig(private_data_dir="/")
    rc.prepare_env()

    assert len(rc.expect_passwords) == 2
    assert TIMEOUT in rc.expect_passwords
    assert rc.expect_passwords[TIMEOUT] is None
    assert EOF in rc.expect_passwords
    assert rc.expect_passwords[EOF] is None


def test_prepare_env_passwords(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig(private_data_dir='/')

    value = {'^SSH [pP]assword.*$': 'secret'}
    password_side_effect = partial(load_file_side_effect, 'env/passwords', value)

    mocker.patch.object(rc.loader, 'load_file', side_effect=password_side_effect)

    rc.prepare_env()
    rc.expect_passwords.pop(TIMEOUT)
    rc.expect_passwords.pop(EOF)
    assert len(rc.expect_passwords) == 1
    assert isinstance(list(rc.expect_passwords.keys())[0], Pattern)
    assert 'secret' in rc.expect_passwords.values()


def test_prepare_env_extra_vars_defaults(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig('/')
    rc.prepare_env()
    assert rc.extra_vars is None


def test_prepare_env_settings_defaults(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig('/')
    rc.prepare_env()
    assert rc.settings == {}


def test_prepare_env_settings(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig('/')

    value = {'test': 'string'}
    settings_side_effect = partial(load_file_side_effect, 'env/settings', value)

    mocker.patch.object(rc.loader, 'load_file', side_effect=settings_side_effect)

    rc.prepare_env()
    assert rc.settings == value


def test_prepare_env_sshkey_defaults(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig('/')
    rc.prepare_env()
    assert rc.ssh_key_data is None


def test_prepare_env_sshkey(mocker):
    mocker.patch('ansible_runner.config._base.open_fifo_write')
    mocker.patch('os.makedirs', return_value=True)
    rc = RunnerConfig('/')

    rsa_key = RSAKey()
    rsa_private_key_value = rsa_key.private
    sshkey_side_effect = partial(load_file_side_effect, 'env/ssh_key', rsa_private_key_value)

    mocker.patch.object(rc.loader, 'load_file', side_effect=sshkey_side_effect)

    rc.prepare_env()
    assert rc.ssh_key_data == rsa_private_key_value


def test_prepare_env_defaults(mocker):
    mocker.patch('os.makedirs', return_value=True)
    path_exists = mocker.patch('os.path.exists')
    path_exists.return_value = True

    rc = RunnerConfig('/')
    rc.prepare_env()
    assert rc.idle_timeout is None
    assert rc.job_timeout is None
    assert rc.pexpect_timeout == 5
    assert rc.cwd == '/project'


def test_prepare_env_directory_isolation(mocker):
    mocker.patch('os.makedirs', return_value=True)
    path_exists = mocker.patch('os.path.exists')
    path_exists.return_value = True

    rc = RunnerConfig('/')
    rc.directory_isolation_path = '/tmp/foo'
    rc.prepare_env()
    assert rc.cwd == '/tmp/foo'


def test_prepare_env_directory_isolation_from_settings(mocker, project_fixtures):
    '''
    Test that sandboxing with directory isolation works correctly with `env/settings` values.
    '''
    # Mock away the things that would actually prepare the isolation directory.
    mocker.patch('os.makedirs', return_value=True)
    copy_tree = mocker.patch('shutil.copytree')
    mkdtemp = mocker.patch('tempfile.mkdtemp')
    mkdtemp.return_value = '/tmp/runner/runner_di_XYZ'
    mocker.patch('ansible_runner.config.runner.RunnerConfig.build_process_isolation_temp_dir')

    # The `directory_isolation` test data sets up an `env/settings` file for us.
    private_data_dir = project_fixtures / 'directory_isolation'
    rc = RunnerConfig(private_data_dir=str(private_data_dir), playbook='main.yaml')

    # This is where all the magic happens
    rc.prepare()

    assert rc.sandboxed
    assert rc.process_isolation_executable == 'bwrap'
    assert rc.project_dir == str(private_data_dir / 'project')
    assert os.path.exists(rc.project_dir)

    # `directory_isolation_path` should be used to create a new temp path underneath
    assert rc.directory_isolation_path == '/tmp/runner/runner_di_XYZ'
    mkdtemp.assert_called_once_with(prefix='runner_di_', dir='/tmp/runner')

    # The project files should be copied to the isolation path.
    copy_tree.assert_called_once_with(rc.project_dir, rc.directory_isolation_path, symlinks=True)


def test_prepare_inventory(mocker):
    mocker.patch('os.makedirs', return_value=True)
    path_exists = mocker.patch('os.path.exists', return_value=True)

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


@pytest.mark.parametrize(
    'extra_vars, expected',
    (
        ({'test': 'key'}, ['ansible-playbook', '-i', '/inventory', '-e', '@/env/extravars', '-e', '{"test":"key"}', 'main.yaml']),
        ('/tmp/extravars.yml', ['ansible-playbook', '-i', '/inventory', '-e', '@/env/extravars', '-e', '@/tmp/extravars.yml', 'main.yaml']),
        (None, ['ansible-playbook', '-i', '/inventory', '-e', '@/env/extravars', 'main.yaml']),
    )
)
def test_generate_ansible_command_extra_vars(mocker, extra_vars, expected):
    mocker.patch('os.makedirs', return_value=True)
    mocker.patch('os.path.exists', return_value=True)

    rc = RunnerConfig(private_data_dir='/', playbook='main.yaml')
    rc.inventory = '/inventory'
    rc.prepare_inventory()

    mocker.patch.object(rc.loader, 'isfile', side_effect=lambda x: True)

    rc.extra_vars = extra_vars
    cmd = rc.generate_ansible_command()
    assert cmd == expected


def test_generate_ansible_command(mocker):
    mocker.patch('os.makedirs', return_value=True)
    mocker.patch('os.path.exists', return_value=True)

    rc = RunnerConfig(private_data_dir='/', playbook='main.yaml')
    rc.prepare_inventory()
    rc.extra_vars = None

    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', 'main.yaml']

    rc.extra_vars = dict(test="key")
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', '-e', '{"test":"key"}', 'main.yaml']
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

    mocker.patch('os.path.exists', return_value=False)
    rc.prepare_inventory()
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', 'main.yaml']

    rc.verbosity = 3
    mocker.patch('os.path.exists', return_value=True)
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


def test_generate_ansible_command_with_api_extravars(mocker):
    mocker.patch('os.makedirs', return_value=True)
    rc = RunnerConfig(private_data_dir='/', playbook='main.yaml', extravars={"foo": "bar"})
    path_exists = mocker.patch('os.path.exists')
    path_exists.return_value = True

    rc.prepare_inventory()

    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', '-e', '{"foo":"bar"}', 'main.yaml']


def test_generate_ansible_command_with_dict_extravars(mocker):
    mocker.patch('os.makedirs', return_value=True)
    rc = RunnerConfig(private_data_dir='/', playbook='main.yaml', extravars={"foo": "test \n hello"})
    path_exists = mocker.patch('os.path.exists')
    path_exists.return_value = True

    rc.prepare_inventory()

    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', '-e', '{"foo":"test \\n hello"}', 'main.yaml']


@pytest.mark.parametrize('cmdline,tokens', [
    (u'--tags foo --skip-tags', ['--tags', 'foo', '--skip-tags']),
    (u'--limit "䉪ቒ칸ⱷ?噂폄蔆㪗輥"', ['--limit', '䉪ቒ칸ⱷ?噂폄蔆㪗輥']),
])
def test_generate_ansible_command_with_cmdline_args(cmdline, tokens, mocker):
    mocker.patch('os.makedirs', return_value=True)
    rc = RunnerConfig(private_data_dir='/', playbook='main.yaml')
    path_exists = mocker.patch('os.path.exists')
    path_exists.return_value = True

    rc.prepare_inventory()
    rc.extra_vars = {}

    cmdline_side_effect = partial(load_file_side_effect, 'env/cmdline', cmdline)
    mocker.patch.object(rc.loader, 'load_file', side_effect=cmdline_side_effect)

    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook'] + tokens + ['-i', '/inventory', 'main.yaml']


def test_prepare_command_defaults(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig('/')

    cmd_side_effect = partial(load_file_side_effect, 'args')

    def generate_side_effect():
        return StringIO(u'test "string with spaces"')

    mocker.patch.object(rc.loader, 'load_file', side_effect=cmd_side_effect)
    mocker.patch.object(rc, 'generate_ansible_command', side_effect=generate_side_effect)

    rc.prepare_command()
    rc.command == ['test', '"string with spaces"']


def test_prepare_with_defaults(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig('/')

    rc.prepare_inventory = mocker.Mock()
    rc.prepare_env = mocker.Mock()
    rc.prepare_command = mocker.Mock()

    rc.ssh_key_data = None
    rc.artifact_dir = '/'
    rc.env = {}

    with pytest.raises(ConfigurationError) as exc:
        rc.prepare()

    assert str(exc.value) == 'No executable for runner to run'


def test_prepare(mocker):
    mocker.patch.dict('os.environ', {
        'AWX_LIB_DIRECTORY': '/awx_lib_directory_via_environ',
    })
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig('/')
    rc.prepare_inventory = mocker.Mock()
    rc.prepare_command = mocker.Mock()
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


def test_prepare_with_ssh_key(mocker):
    mocker.patch('os.makedirs', return_value=True)
    open_fifo_write_mock = mocker.patch('ansible_runner.config._base.open_fifo_write')
    rc = RunnerConfig('/')

    rc.prepare_inventory = mocker.Mock()
    rc.prepare_command = mocker.Mock()

    rc.wrap_args_with_ssh_agent = mocker.Mock()

    rc.ssh_key_data = None
    rc.artifact_dir = '/'
    rc.env = {}
    rc.execution_mode = ExecutionMode.ANSIBLE_PLAYBOOK
    rc.playbook = 'main.yaml'
    rsa_key = RSAKey()
    rc.ssh_key_data = rsa_key.private
    rc.command = 'ansible-playbook'

    mocker.patch.dict('os.environ', {'AWX_LIB_DIRECTORY': '/'})

    rc.prepare()

    assert rc.ssh_key_path == '/ssh_key_data'
    assert rc.wrap_args_with_ssh_agent.called
    assert open_fifo_write_mock.called


def test_wrap_args_with_ssh_agent_defaults(mocker):
    mocker.patch('os.makedirs', return_value=True)
    rc = RunnerConfig('/')
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], '/tmp/sshkey')
    assert res == [
        'ssh-agent',
        'sh', '-c',
        "trap 'rm -f /tmp/sshkey' EXIT && ssh-add /tmp/sshkey && rm -f /tmp/sshkey && ansible-playbook main.yaml"
    ]


def test_wrap_args_with_ssh_agent_with_auth(mocker):
    mocker.patch('os.makedirs', return_value=True)
    rc = RunnerConfig('/')
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], '/tmp/sshkey', '/tmp/sshauth')
    assert res == [
        'ssh-agent', '-a', '/tmp/sshauth',
        'sh', '-c',
        "trap 'rm -f /tmp/sshkey' EXIT && ssh-add /tmp/sshkey && rm -f /tmp/sshkey && ansible-playbook main.yaml"
    ]


def test_wrap_args_with_ssh_agent_silent(mocker):
    mocker.patch('os.makedirs', return_value=True)
    rc = RunnerConfig('/')
    res = rc.wrap_args_with_ssh_agent(['ansible-playbook', 'main.yaml'], '/tmp/sshkey', silence_ssh_add=True)
    assert res == [
        'ssh-agent',
        'sh', '-c',
        "trap 'rm -f /tmp/sshkey' EXIT && ssh-add /tmp/sshkey 2>/dev/null && rm -f /tmp/sshkey && ansible-playbook main.yaml"
    ]


@pytest.mark.parametrize('executable_present', [True, False])
def test_process_isolation_executable_not_found(executable_present, mocker):
    mocker.patch('ansible_runner.runner_config.RunnerConfig.prepare')
    mock_sys = mocker.patch('ansible_runner.interface.sys')
    mock_subprocess = mocker.patch('ansible_runner.utils.subprocess')
    # Mock subprocess.Popen indicates if
    # process isolation executable is present
    mock_proc = mocker.Mock()
    mock_proc.returncode = (0 if executable_present else 1)
    mock_subprocess.Popen.return_value = mock_proc

    kwargs = {'process_isolation': True,
              'process_isolation_executable': 'fake_executable'}
    init_runner(**kwargs)
    if executable_present:
        assert not mock_sys.exit.called
    else:
        assert mock_sys.exit.called


def test_bwrap_process_isolation_defaults(mocker):
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig('/')
    rc.artifact_dir = '/tmp/artifacts'
    rc.playbook = 'main.yaml'
    rc.command = 'ansible-playbook'
    rc.process_isolation = True
    rc.process_isolation_executable = 'bwrap'

    path_exists = mocker.patch('os.path.exists')
    path_exists.return_value = True

    rc.prepare()

    assert rc.command == [
        'bwrap',
        '--die-with-parent',
        '--unshare-pid',
        '--dev-bind', '/dev', 'dev',
        '--proc', '/proc',
        '--dir', '/tmp',
        '--ro-bind', '/bin', '/bin',
        '--ro-bind', '/etc', '/etc',
        '--ro-bind', '/usr', '/usr',
        '--ro-bind', '/opt', '/opt',
        '--symlink', 'usr/lib64', '/lib64',
        '--bind', '/', '/',
        '--chdir', '/project',
        'ansible-playbook', '-i', '/inventory', 'main.yaml',
    ]


def test_bwrap_process_isolation_and_directory_isolation(mocker, patch_private_data_dir, tmp_path):

    def mock_exists(path):
        if path == "/project":
            return False
        return True

    class MockArtifactLoader:
        def __init__(self, base_path):
            self.base_path = base_path

        def load_file(self, path, objtype=None, encoding='utf-8'):
            raise ConfigurationError

        def isfile(self, path):
            return False

    mocker.patch('ansible_runner.config.runner.os.makedirs', return_value=True)
    mocker.patch('ansible_runner.config.runner.os.chmod', return_value=True)
    mocker.patch('ansible_runner.config.runner.os.path.exists', mock_exists)
    mocker.patch('ansible_runner.config._base.ArtifactLoader', new=MockArtifactLoader)

    artifact_path = tmp_path / 'artifacts'
    artifact_path.mkdir()

    rc = RunnerConfig('/')
    rc.artifact_dir = tmp_path / 'artifacts'
    rc.directory_isolation_path = tmp_path / 'dirisolation'
    rc.playbook = 'main.yaml'
    rc.command = 'ansible-playbook'
    rc.process_isolation = True
    rc.process_isolation_executable = 'bwrap'

    rc.prepare()

    assert rc.command == [
        'bwrap',
        '--die-with-parent',
        '--unshare-pid',
        '--dev-bind', '/dev', 'dev',
        '--proc', '/proc',
        '--dir', '/tmp',
        '--ro-bind', '/bin', '/bin',
        '--ro-bind', '/etc', '/etc',
        '--ro-bind', '/usr', '/usr',
        '--ro-bind', '/opt', '/opt',
        '--symlink', 'usr/lib64', '/lib64',
        '--bind', '/', '/',
        '--chdir', os.path.realpath(rc.directory_isolation_path),
        'ansible-playbook', '-i', '/inventory', 'main.yaml',
    ]


def test_process_isolation_settings(mocker, tmp_path):
    mocker.patch('os.path.isdir', return_value=False)
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('os.makedirs', return_value=True)

    rc = RunnerConfig('/')
    rc.artifact_dir = tmp_path.joinpath('artifacts').as_posix()
    rc.playbook = 'main.yaml'
    rc.command = 'ansible-playbook'
    rc.process_isolation = True
    rc.process_isolation_executable = 'not_bwrap'
    rc.process_isolation_hide_paths = ['/home', '/var']
    rc.process_isolation_show_paths = ['/usr']
    rc.process_isolation_ro_paths = ['/venv']
    rc.process_isolation_path = tmp_path.as_posix()

    mocker.patch('os.path.exists', return_value=True)

    rc.prepare()
    print(rc.command)
    expected = [
        'not_bwrap',
        '--die-with-parent',
        '--unshare-pid',
        '--dev-bind', '/dev', 'dev',
        '--proc', '/proc',
        '--dir', '/tmp',
        '--ro-bind', '/bin', '/bin',
        '--ro-bind', '/etc', '/etc',
        '--ro-bind', '/usr', '/usr',
        '--ro-bind', '/opt', '/opt',
        '--symlink', 'usr/lib64', '/lib64',
    ]
    index = len(expected)
    assert rc.command[0:index] == expected

    # hide /home
    assert rc.command[index] == '--bind'
    assert 'ansible_runner_pi' in rc.command[index + 1]
    assert rc.command[index + 2] == os.path.realpath('/home')  # needed for Mac

    # hide /var
    assert rc.command[index + 3] == '--bind'
    assert 'ansible_runner_pi' in rc.command[index + 4]
    assert rc.command[index + 5] in ('/var', '/private/var')

    # read-only bind
    assert rc.command[index + 6:index + 9] == ['--ro-bind', '/venv', '/venv']

    # root bind
    assert rc.command[index + 9:index + 12] == ['--bind', '/', '/']

    # show /usr
    assert rc.command[index + 12:index + 15] == ['--bind', '/usr', '/usr']

    # chdir and ansible-playbook command
    assert rc.command[index + 15:] == ['--chdir', '/project', 'ansible-playbook', '-i', '/inventory', 'main.yaml']


def test_container_volume_mounting_with_Z(mocker, tmp_path):
    mocker.patch('os.path.isdir', return_value=True)
    mocker.patch('os.path.exists', return_value=True)

    rc = RunnerConfig(str(tmp_path))
    rc.container_volume_mounts = ['/tmp/project_path:/tmp/project_path:Z']
    rc.container_name = 'foo'
    rc.env = {}
    new_args = rc.wrap_args_for_containerization(['ansible-playbook', 'foo.yml'], 0, None)
    assert new_args[0] == 'podman'
    for i, entry in enumerate(new_args):
        if entry == '-v':
            mount = new_args[i + 1]
            if mount.endswith(':/tmp/project_path/:Z'):
                break
    else:
        raise Exception('Could not find expected mount, args: {}'.format(new_args))


@pytest.mark.parametrize('runtime', ('docker', 'podman'))
def test_containerization_settings(tmp_path, runtime, mocker):
    mocker.patch('os.path.isdir', return_value=True)
    mocker.patch('os.path.exists', return_value=True)
    mock_containerized = mocker.patch('ansible_runner.runner_config.RunnerConfig.containerized', new_callable=mocker.PropertyMock)
    mock_containerized.return_value = True

    # In this test get_callback_dir() will not return a callback plugin dir that exists
    # mock shutil.copytree and shutil.rmtree to just return True instead of trying to copy
    mocker.patch('shutil.copytree', return_value=True)
    mocker.patch('shutil.rmtree', return_value=True)

    rc = RunnerConfig(tmp_path)
    rc.ident = 'foo'
    rc.playbook = 'main.yaml'
    rc.command = 'ansible-playbook'
    rc.process_isolation = True
    rc.process_isolation_executable = runtime
    rc.container_image = 'my_container'
    rc.container_volume_mounts = ['/host1:/container1', '/host2:/container2']
    rc.prepare()

    # validate ANSIBLE_CALLBACK_PLUGINS env var is set
    assert rc.env.get('ANSIBLE_CALLBACK_PLUGINS', None) is not None

    # validate ANSIBLE_CALLBACK_PLUGINS contains callback plugin dir
    callback_plugins = rc.env['ANSIBLE_CALLBACK_PLUGINS'].split(':')
    callback_dir = os.path.join("/runner/artifacts", "{}".format(rc.ident), "callback")
    assert callback_dir in callback_plugins

    extra_container_args = []
    if runtime == 'podman':
        extra_container_args = ['--quiet']
    else:
        extra_container_args = [f'--user={os.getuid()}']

    expected_command_start = [runtime, 'run', '--rm', '--tty', '--interactive', '--workdir', '/runner/project'] + \
        ['-v', '{}/:/runner/:Z'.format(rc.private_data_dir)] + \
        ['-v', '/host1/:/container1/', '-v', '/host2/:/container2/'] + \
        ['--env-file', '{}/env.list'.format(rc.artifact_dir)] + \
        extra_container_args + \
        ['--name', 'ansible_runner_foo'] + \
        ['my_container', 'ansible-playbook', '-i', '/runner/inventory/hosts', 'main.yaml']

    assert expected_command_start == rc.command
