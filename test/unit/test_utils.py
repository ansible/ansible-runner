import json
import shutil

from pytest import raises
from mock import patch

from ansible_runner.utils import isplaybook, isinventory
from ansible_runner.utils import dump_artifacts


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
    data_dir = '/tmp'
    kwargs = {'private_data_dir': data_dir}
    dump_artifacts(kwargs)
    assert kwargs['private_data_dir'] == data_dir

    kwargs = {'private_data_dir': None}
    dump_artifacts(kwargs)
    assert kwargs['private_data_dir'].startswith('/tmp/tmp')
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
