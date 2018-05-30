
from ansible_runner.runner_config import RunnerConfig
from mock import patch
import re
from collections import Mapping
from six import string_types
from pexpect import TIMEOUT, EOF


def envvar_side_effect(*args, **kwargs):
    if args[0] == 'env/envvars':
        return dict(A=1, B=True, C="foo")
    elif args[1] == Mapping:
        return dict()
    elif args[1] == string_types:
        return ""
    else:
        return None


def password_side_effect(*args, **kwargs):
    if args[0] == 'env/passwords':
        return {'^SSH [pP]assword.*$': 'secret'}
    elif args[1] == Mapping:
        return dict()
    elif args[1] == string_types:
        return ""
    else:
        return None



def test_prepare_environment_vars_only_strings():
    rc = RunnerConfig(private_data_dir="/")
    with patch.object(rc.loader, 'load_file', side_effect=envvar_side_effect):
        rc.prepare_env()
        assert 'A' in rc.env
        assert isinstance(rc.env['A'], string_types)
        assert 'B' in rc.env
        assert isinstance(rc.env['B'], string_types)
        assert 'C' in rc.env
        assert isinstance(rc.env['C'], string_types)


def test_prepare_environment_pexpect_defaults():
    rc = RunnerConfig(private_data_dir="/")
    with patch.object(rc.loader, 'load_file', side_effect=envvar_side_effect):
        rc.prepare_env()
        assert TIMEOUT in rc.expect_passwords
        assert EOF in rc.expect_passwords


def test_prepare_env_passwords():
    rc = RunnerConfig(private_data_dir='/')
    with patch.object(rc.loader, 'load_file', side_effect=password_side_effect):
        rc.prepare_env()
        rc.expect_passwords.pop(TIMEOUT)
        rc.expect_passwords.pop(EOF)
        assert len(rc.expect_passwords) == 1
        assert isinstance(list(rc.expect_passwords.keys())[0], re._pattern_type)
        assert 'secret' in rc.expect_passwords.values()
