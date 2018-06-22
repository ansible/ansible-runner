import json
import shutil
import tempfile

from pytest import raises
from mock import patch

from ansible_runner.exceptions import AnsibleRunnerException
from ansible_runner.utils import isplaybook, isinventory
from ansible_runner.utils import dump_artifacts
from ansible_runner.utils import validate_ssh_key


def test_isplaybook():

    for obj in ('foo', {}, {'foo': 'bar'}, True, False, None):
        assert isplaybook(obj) is False, obj

    for obj in (['foo'], []):
        assert isplaybook(obj) is True, obj


def test_isinventory():
    for obj in (__file__, {}, {'foo': 'bar'}):
        assert isinventory(obj) is True, obj

    for obj in ([], ['foo'], True, False, None):
        assert isinventory(obj) is False, obj


def test_dump_artifacts_private_data_dir():
    data_dir = tempfile.gettempdir()
    kwargs = {'private_data_dir': data_dir}
    dump_artifacts(kwargs)
    assert kwargs['private_data_dir'] == data_dir

    kwargs = {'private_data_dir': None}
    dump_artifacts(kwargs)
    assert kwargs['private_data_dir'].startswith(tempfile.gettempdir())
    shutil.rmtree(kwargs['private_data_dir'])

    with raises(ValueError):
        data_dir = '/foo'
        kwargs = {'private_data_dir': data_dir}
        dump_artifacts(kwargs)


def test_dump_artifacts_playbook():
    with patch('ansible_runner.utils.dump_artifact') as mock_dump_artifact:
        # playbook as a native object
        pb = [{'playbook': [{'hosts': 'all'}]}]
        kwargs = {'private_data_dir': '/tmp', 'playbook': pb}
        dump_artifacts(kwargs)
        assert mock_dump_artifact.call_count == 1
        data, fp, fn = mock_dump_artifact.call_args[0]
        assert data == json.dumps(pb)
        assert fp == '/tmp/project'
        assert fn == 'main.json'

        mock_dump_artifact.reset_mock()

        # playbook as a path
        pb = 'test.yml'
        kwargs = {'private_data_dir': '/tmp', 'playbook': pb}
        dump_artifacts(kwargs)
        assert mock_dump_artifact.call_count == 0
        assert mock_dump_artifact.called is False

        mock_dump_artifact.reset_mock()

        # invalid playbook structures
        for obj in ({'foo': 'bar'}, None, True, False, 'foo', []):
            mock_dump_artifact.reset_mock()
            kwargs = {'private_data_dir': '/tmp', 'playbook': obj}
            dump_artifacts(kwargs)
            assert mock_dump_artifact.call_count == 0
            assert mock_dump_artifact.called is False


def test_dump_artifacts_inventory():
    with patch('ansible_runner.utils.dump_artifact') as mock_dump_artifact:
        # inventory as a string (INI)
        inv = '[all]\nlocalhost'
        kwargs = {'private_data_dir': '/tmp', 'inventory': inv}
        dump_artifacts(kwargs)
        assert mock_dump_artifact.call_count == 1
        data, fp, fn = mock_dump_artifact.call_args[0]
        assert data == inv
        assert fp == '/tmp/inventory'
        assert fn == 'hosts'

        mock_dump_artifact.reset_mock()

        # inventory as a path
        inv = '/tmp'
        kwargs = {'private_data_dir': '/tmp', 'inventory': inv}
        dump_artifacts(kwargs)
        assert mock_dump_artifact.call_count == 0
        assert mock_dump_artifact.called is False
        assert kwargs['inventory'] == inv

        mock_dump_artifact.reset_mock()

        # inventory as a native object
        inv = {'foo': 'bar'}
        kwargs = {'private_data_dir': '/tmp', 'inventory': inv}
        dump_artifacts(kwargs)
        assert mock_dump_artifact.call_count == 1
        data, fp, fn = mock_dump_artifact.call_args[0]
        assert data == json.dumps(inv)
        assert fp == '/tmp/inventory'
        assert fn == 'hosts.json'


def test_dump_artifacts_extravars():
    with patch('ansible_runner.utils.dump_artifact') as mock_dump_artifact:
        extravars = {'foo': 'bar'}
        kwargs = {'private_data_dir': '/tmp', 'extravars': extravars}
        dump_artifacts(kwargs)
        assert mock_dump_artifact.call_count == 1
        data, fp, fn = mock_dump_artifact.call_args[0]
        assert data == json.dumps(extravars)
        assert fp == '/tmp/env'
        assert fn == 'extravars'
        assert 'extravars' not in kwargs


def test_dump_artifacts_passwords():
    with patch('ansible_runner.utils.dump_artifact') as mock_dump_artifact:
        passwords = {'foo': 'bar'}
        kwargs = {'private_data_dir': '/tmp', 'passwords': passwords}
        dump_artifacts(kwargs)
        assert mock_dump_artifact.call_count == 1
        data, fp, fn = mock_dump_artifact.call_args[0]
        assert data == json.dumps(passwords)
        assert fp == '/tmp/env'
        assert fn == 'passwords'
        assert 'passwords' not in kwargs


def test_dump_artifacts_settings():
    with patch('ansible_runner.utils.dump_artifact') as mock_dump_artifact:
        settings = {'foo': 'bar'}
        kwargs = {'private_data_dir': '/tmp', 'settings': settings}
        dump_artifacts(kwargs)
        assert mock_dump_artifact.call_count == 1
        data, fp, fn = mock_dump_artifact.call_args[0]
        assert data == json.dumps(settings)
        assert fp == '/tmp/env'
        assert fn == 'settings'
        assert 'settings' not in kwargs


def test_dump_artifacts_ssh_key():
    with patch('ansible_runner.utils.dump_artifact') as mock_dump_artifact:
        ssh_key = '1234567890'
        kwargs = {'private_data_dir': '/tmp', 'ssh_key': ssh_key}
        dump_artifacts(kwargs)
        assert mock_dump_artifact.call_count == 1
        data, fp, fn = mock_dump_artifact.call_args[0]
        assert data == ssh_key
        assert fp == '/tmp/env'
        assert fn == 'ssh_key'
        assert 'ssh_key' not in kwargs


def test_valid_ssh_key():
    ssh_key = """-----BEGIN RSA PRIVATE KEY-----
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
-----END RSA PRIVATE KEY-----"""
    assert isinstance(validate_ssh_key(ssh_key), dict)


def test_non_key():
    ssh_key = "This is not a key"
    with raises(AnsibleRunnerException):
        validate_ssh_key(ssh_key)


def test_invalid_base64_key():
    ssh_key = """-----BEGIN RSA PRIVATE KEY-----This is not base 64-----END RSA PRIVATE KEY-----"""
    with raises(AnsibleRunnerException):
        validate_ssh_key(ssh_key)
