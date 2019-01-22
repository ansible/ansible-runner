import json
import shutil
import tempfile
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

from pytest import raises
from mock import patch

from ansible_runner.utils import isplaybook, isinventory
from ansible_runner.utils import dump_artifacts
from ansible_runner.utils import OutputVerboseFilter


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


def test_dump_artifacts_roles():
    with patch('ansible_runner.utils.dump_artifact') as mock_dump_artifact:
        kwargs = dict(private_data_dir="/tmp",
                      role="test",
                      playbook=[{'playbook': [{'hosts': 'all'}]}])
        dump_artifacts(kwargs)
        assert mock_dump_artifact.call_count == 2
        data, envpath, fp = mock_dump_artifact.call_args[0]
        assert fp == "envvars"
        data = json.loads(data)
        assert "ANSIBLE_ROLES_PATH" in data
        assert data['ANSIBLE_ROLES_PATH'] == "/tmp/roles"
        mock_dump_artifact.reset_mock()
        kwargs = dict(private_data_dir="/tmp",
                      role="test",
                      roles_path="/tmp/altrole",
                      playbook=[{'playbook': [{'hosts': 'all'}]}])
        dump_artifacts(kwargs)
        assert mock_dump_artifact.call_count == 2
        data, envpath, fp = mock_dump_artifact.call_args[0]
        assert fp == "envvars"
        data = json.loads(data)
        assert "ANSIBLE_ROLES_PATH" in data
        assert data['ANSIBLE_ROLES_PATH'] == "/tmp/altrole:/tmp/roles"


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


def test_dump_artifacts_cmdline():
    with patch('ansible_runner.utils.dump_artifact') as mock_dump_artifact:
        cmdline = '--tags foo --skip-tags'
        kwargs = {'private_data_dir': '/tmp', 'cmdline': cmdline}
        dump_artifacts(kwargs)
        assert mock_dump_artifact.call_count == 1
        data, fp, fn = mock_dump_artifact.call_args[0]
        assert data == cmdline
        assert fp == '/tmp/env'
        assert fn == 'cmdline'
        assert 'cmdline' not in kwargs


def test_verbose_line_buffering():
    events = []

    def _callback(event_data):
        events.append(event_data)

    stdout_handler = StringIO()
    f = OutputVerboseFilter(stdout_handler, _callback)
    f.write('one two\r\n\r\n')

    assert len(events) == 2
    assert events[0]['start_line'] == 0
    assert events[0]['end_line'] == 1
    assert events[0]['stdout'] == 'one two'

    assert events[1]['start_line'] == 1
    assert events[1]['end_line'] == 2
    assert events[1]['stdout'] == ''

    f.write('three')
    assert len(events) == 2
    f.write('\r\nfou')

    # three is not pushed to buffer until its line completes
    assert len(events) == 3
    assert events[2]['start_line'] == 2
    assert events[2]['end_line'] == 3
    assert events[2]['stdout'] == 'three'

    f.write('r\r')
    f.write('\nfi')

    assert events[3]['start_line'] == 3
    assert events[3]['end_line'] == 4
    assert events[3]['stdout'] == 'four'

    f.write('ve')
    f.write('\r\n')

    assert len(events) == 5
    assert events[4]['start_line'] == 4
    assert events[4]['end_line'] == 5
    assert events[4]['stdout'] == 'five'

    f.close()

    from pprint import pprint
    pprint(events)
    assert len(events) == 6

    assert events[5]['event'] == 'EOF'
