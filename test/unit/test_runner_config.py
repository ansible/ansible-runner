import os
import re

from functools import partial

from six import string_types
from pexpect import TIMEOUT, EOF

from pytest import raises
from mock import patch
from mock import Mock

from ansible_runner.runner_config import RunnerConfig
from ansible_runner.loader import ArtifactLoader
from ansible_runner.exceptions import ConfigurationError


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
    assert rc.logger is not None
    assert isinstance(rc.loader, ArtifactLoader)


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
    assert rc.logger is not None
    assert isinstance(rc.loader, ArtifactLoader)


def test_prepare_environment_vars_only_strings():
    rc = RunnerConfig(private_data_dir="/")

    value = dict(A=1, B=True, C="foo")
    envvar_side_effect = partial(load_file_side_effect, 'env/envvars', value)

    with patch.object(rc.loader, 'load_file', side_effect=envvar_side_effect):
        rc.prepare_env()
        assert 'A' in rc.env
        assert isinstance(rc.env['A'], string_types)
        assert 'B' in rc.env
        assert isinstance(rc.env['B'], string_types)
        assert 'C' in rc.env
        assert isinstance(rc.env['C'], string_types)


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
        assert isinstance(list(rc.expect_passwords.keys())[0], re._pattern_type)
        assert 'secret' in rc.expect_passwords.values()


def test_prepare_env_extra_vars_defaults():
    rc = RunnerConfig('/')
    rc.prepare_env()
    assert rc.extra_vars == {}


def test_prepare_env_extra_vars():
    rc = RunnerConfig('/')

    value = {'test': 'string'}
    extravars_side_effect = partial(load_file_side_effect, 'env/extravars', value)

    with patch.object(rc.loader, 'load_file', side_effect=extravars_side_effect):
        rc.prepare_env()
        assert rc.extra_vars  == value


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

    value = '''-----BEGIN RSA PRIVATE KEY-----
MIIEogIBAAKCAQEAxsB2TfnP9c9uHotCTe7hTjA67xDbGT7gl650v7PMOQTS6azx
MhYw8rynuSJXognjM/oSWmTvAn5BsLsYThmORYOCD/qmmqQfhfi6K5UOIynqH5VX
y2zBPgK98T7hpivlj2IsUYG2LENTDAt7soac+SdmSu/ogRS4Cp43n46H8jtZ97Hk
b+bT1WXCT9175/hjFFDxa6Y3RjzS+47rAjeIDHL15ANHf8FbpH7EtIv5BbkVeJjg
50p21HmG408XzmvFkE8FDpx36NMJjLeZY2+Fbej1KaLw/xLhmytOXbMR2IDJT5PG
GsWgxcpOPy7ai4AL+WqXNUZx5OS3xPkcJ8w1iQIDAQABAoIBAHoXktU1x7Vl1my2
+WUsgIVqhVmEjkNE5+zlw1xcE/FW8EWR8pzlGu6SS6oj2Zd14Xd1gD69UEHE04/A
bx7S/h3fuk8cl6nZdm/zKlJJf2TEg8khEcyqI093mb0P9sgAoUVidn0fZIxuUx7M
ExHJNbasqF8SX06kLqZ/KQZAJWz8SZQjrWLxFsX4xztzzMWPaV7bBkSrqYOgFvGh
YIALvsOaDOeXdYg4LNtykdB7jb098FQ1Cg1ALL8+a/QZf6P+vTRiDyMFdvSWbYQY
DYmqnsHeoolwUpZDVKQyjQ4mXSyHlIuPt0wLoES6AfBmqluUjCzXKRlkZ4nonZKk
620PCIECgYEA45/VXcWR9wp5JTBTOLtYmPIk9Ha62tM43j4PLQPqo5FNMxkyMhiU
G3kTrjB4hRPyuvyo0cweKaarIdyyM3JoGRRBkHpUJWehZhL/8mzFO6rRQX8hdzfO
hIxTTl5LI5IGdfTA7VfZIkp03gMyFGFMtGkatc3MPxEra8AiQvs6KTkCgYEA34c4
aGF00UBCm/bk7nWxOdZYv0JLRSeympsLef7oxINVHkQo77W/j3dxFSlBw0jpcBWK
CU4X1RpAc59UddViAxWsfIB27sDgB1tJav0mcqiwMLSeAFCRPglI8AAyuxMgIawg
PAsVkfGjUSzbHKsz4lR161vOQZ2dlqaay426/tECgYAVAYsPPExcH/tOE0ea1K84
biA67zoPN67n05JS9SmSLraRIKIhPWNtpZ7LVG3K2ixsVSS/N7cQ4PCqD1Piq4wv
xE7IpoFdclLSuK4mESOifgERqknMVroYQVruwITuo2s1N4EWZiUDpRtj4aeded06
SPjODk/rAgqfxvticwzLAQKBgHP93y+LIutSxT3ZqIJ1YDn7GKJm7Fg+eVfxDMuJ
k5Al9o12ISgC0BzKhkvM1OtZcolPJAogFA3pSXi2PUXILMwc+xzALPdH7vjiTf7O
zpzBHGypzTOsmzHt74NbFvgsvIe8oh2GQvMwyObet/TwgkP4QBiZ0zYJbDU4zyrB
qT+BAoGAQ3+6hyWYhWijOSrSGG1RhL9j+kLZP5lIEGNIgxe2hIb0C39uAas/W0Yv
ipUvkv0tGIsSOStuIg5tA6lNviTA6xBSb4XYKrr6wDEqENjFKle8oHhtTy2t6BZl
nsYDJfgRDy4Du8FikB5yEP4RsfY7diXpmOOKggORuK9OZ9nYp/w=
-----END RSA PRIVATE KEY-----'''
    sshkey_side_effect = partial(load_file_side_effect, 'env/ssh_key', value)

    with patch.object(rc.loader, 'load_key', side_effect=sshkey_side_effect):
        rc.prepare_env()
        assert rc.ssh_key_data == value


def test_prepare_env_defaults():
    rc = RunnerConfig('/')
    rc.prepare_env()

    assert rc.idle_timeout == 120
    assert rc.job_timeout == 120
    assert rc.pexpect_timeout == 5
    assert rc.cwd == '/project'


def test_prepare_inventory():
    rc = RunnerConfig(private_data_dir='/')
    rc.prepare_inventory()
    assert rc.inventory == '/inventory'
    rc.inventory = '/tmp/inventory'
    rc.prepare_inventory()
    assert rc.inventory == '/tmp/inventory'


def test_generate_ansible_command():
    rc = RunnerConfig(private_data_dir='/', playbook='main.yaml')
    rc.prepare_inventory()

    rc.extra_vars = None
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', 'main.yaml']

    rc.extra_vars = {'test': 'string'}
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', '-e', 'test=string', 'main.yaml']

    rc.extra_vars = None
    rc.limit = 'hosts'
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible-playbook', '-i', '/inventory', '--limit', 'hosts', 'main.yaml']

    rc.module = 'setup'
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible', '-i', '/inventory', '--limit', 'hosts', '-m', 'setup']

    rc.module_args = 'test=string'
    cmd = rc.generate_ansible_command()
    assert cmd == ['ansible', '-i', '/inventory', '--limit', 'hosts', '-m', 'setup', '-a', 'test=string']


def test_prepare_command_defaults():
    rc = RunnerConfig('/')

    cmd_side_effect = partial(load_file_side_effect, 'args')

    def generate_side_effect():
        return 'test string'

    with patch.object(rc.loader, 'load_file', side_effect=cmd_side_effect):
        with patch.object(rc, 'generate_ansible_command', side_effect=generate_side_effect):
            rc.prepare_command()
            rc.command == 'test string'


def test_prepare_command_with_args():
    rc = RunnerConfig('/')

    value = 'test string'
    args_side_effect = partial(load_file_side_effect, 'args', value)

    with patch.object(rc.loader, 'load_file', side_effect=args_side_effect):
        rc.prepare_command()
        assert rc.command == value


def test_prepare_with_defaults():
    rc = RunnerConfig('/')

    rc.prepare_inventory = Mock()
    rc.prepare_env = Mock()
    rc.prepare_command = Mock()

    rc.ssh_key_data = None
    rc.artifact_dir = '/'
    rc.env = {}

    with raises(ConfigurationError) as exc:
        rc.prepare()
        assert str(exc) == 'Runner playbook is not defined'


def test_prepare():
    rc = RunnerConfig('/')

    rc.prepare_inventory = Mock()
    rc.prepare_env = Mock()
    rc.prepare_command = Mock()

    rc.ssh_key_data = None
    rc.artifact_dir = '/'
    rc.env = {}
    rc.playbook = 'main.yaml'

    os.environ['AWX_LIB_DIRECTORY'] = '/'

    rc.prepare()

    assert rc.prepare_inventory.called
    assert rc.prepare_env.called
    assert rc.prepare_command.called

    assert not hasattr(rc, 'ssh_key_path')
    assert not hasattr(rc, 'ssh_auth_sock')
    assert not hasattr(rc, 'command')

    assert rc.env['ANSIBLE_STDOUT_CALLBACK'] == 'awx_display'
    assert rc.env['ANSIBLE_RETRY_FILES_ENABLED'] == 'False'
    assert rc.env['ANSIBLE_HOST_KEY_CHECKING'] == 'False'
    assert rc.env['AWX_ISOLATED_DATA_DIR'] == '/'
    assert rc.env['PYTHONPATH'] == '/:'


def test_prepare_with_ssh_key():
    rc = RunnerConfig('/')

    rc.prepare_inventory = Mock()
    rc.prepare_env = Mock()
    rc.prepare_command = Mock()

    rc.wrap_args_with_ssh_agent = Mock()
    rc.open_fifo_write = Mock()

    rc.ssh_key_data = None
    rc.artifact_dir = '/'
    rc.env = {}
    rc.playbook = 'main.yaml'
    rc.ssh_key_data = '01234567890'
    rc.command = 'ansible-playbook'

    os.environ['AWX_LIB_DIRECTORY'] = '/'

    rc.prepare()

    assert rc.ssh_key_path == '/ssh_key_data'
    assert rc.ssh_auth_sock == '/ssh_auth.sock'
    assert rc.wrap_args_with_ssh_agent.called
    assert rc.open_fifo_write.called


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


def test_fifo_write():
    pass


def test_args2cmdline():
    rc = RunnerConfig('/')
    res = rc.args2cmdline('ansible', '-m', 'setup', 'localhost')
    assert res == 'ansible -m setup localhost'
