import json
import os
import shutil
import tempfile
import io

from pathlib import Path

import pytest
from unittest.mock import patch

from ansible_runner.utils import (
    isplaybook,
    isinventory,
    dump_artifacts,
    args2cmdline,
    sanitize_container_name
)
from ansible_runner.utils.streaming import stream_dir, unstream_dir


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

    with pytest.raises(ValueError):
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
        inv = '[all]\nlocalhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"'
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


def test_fifo_write():
    pass


def test_args2cmdline():
    res = args2cmdline('ansible', '-m', 'setup', 'localhost')
    assert res == 'ansible -m setup localhost'


@pytest.mark.parametrize('container_name,expected_name', [
    ('foo?bar', 'foo_bar'),
    ('096aac5c-024d-453e-9725-779dc8b3faee', '096aac5c-024d-453e-9725-779dc8b3faee'),  # uuid4
    (42, '42')  # AWX will use primary keys and may not be careful about type
])
def test_sanitize_container_name(container_name, expected_name):
    sanitize_container_name(str(container_name)) == expected_name


@pytest.mark.parametrize('symlink_dest,check_content', [
    ('/bin', []),
    ('ordinary_file.txt', ['my_link']),
    ('ordinary_directory', ['my_link/dir_file.txt']),
    ('.', ['my_link/ordinary_directory/dir_file.txt', 'my_link/my_link/ordinary_file.txt']),
    ('filedoesnotexist.txt', [])
], ids=['global', 'local', 'directory', 'recursive', 'bad'])
def test_transmit_symlink(tmp_path, symlink_dest, check_content):
    symlink_dest = Path(symlink_dest)

    # prepare the input private_data_dir directory to zip
    pdd = tmp_path / 'symlink_zip_test'
    pdd.mkdir()

    # Create some basic shared demo content
    with open(pdd / 'ordinary_file.txt', 'w') as f:
        f.write('hello world')

    ord_dir = pdd / 'ordinary_directory'
    ord_dir.mkdir()
    with open(ord_dir / 'dir_file.txt', 'w') as f:
        f.write('hello world')

    old_symlink_path = pdd / 'my_link'
    old_symlink_path.symlink_to(symlink_dest)

    # SANITY - set expectations for the symlink
    assert old_symlink_path.is_symlink()
    assert os.readlink(old_symlink_path) == str(symlink_dest)

    # zip and stream the data into the in-memory buffer outgoing_buffer
    outgoing_buffer = io.BytesIO()
    outgoing_buffer.name = 'not_stdout'
    stream_dir(pdd, outgoing_buffer)

    # prepare the destination private_data_dir to transmit to
    dest_dir = tmp_path / 'symlink_zip_dest'
    dest_dir.mkdir()

    # Extract twice so we assure that existing data does not break things
    for i in range(2):

        # rewind the buffer and extract into destination private_data_dir
        outgoing_buffer.seek(0)
        first_line = outgoing_buffer.readline()
        size_data = json.loads(first_line.strip())
        unstream_dir(outgoing_buffer, size_data['zipfile'], dest_dir)

        # Assure the new symlink is still the same type of symlink
        new_symlink_path = dest_dir / 'my_link'
        assert new_symlink_path.is_symlink()
        assert os.readlink(new_symlink_path) == str(symlink_dest)

    for fname in check_content:
        abs_path = dest_dir / fname
        assert abs_path.exists(), f'Expected "{fname}" in target dir to be a file with content.'
        with open(abs_path, 'r') as f:
            assert f.read() == 'hello world'


@pytest.mark.parametrize('fperm', [
    0o777,
    0o666,
    0o555,
    0o700,
])
def test_transmit_permissions(tmp_path, fperm):
    # breakpoint()
    pdd = tmp_path / 'transmit_permission_test'
    pdd.mkdir()

    old_file_path = pdd / 'ordinary_file.txt'
    with open(old_file_path, 'w') as f:
        f.write('hello world')
    old_file_path.chmod(fperm)

    # SANITY - set expectations for the file
    # assert oct(os.stat(old_file_path).st_mode & 0o777) == oct(fperm)
    assert oct(old_file_path.stat().st_mode & 0o777) == oct(fperm)

    outgoing_buffer = io.BytesIO()
    outgoing_buffer.name = 'not_stdout'
    stream_dir(pdd, outgoing_buffer)

    dest_dir = tmp_path / 'transmit_permission_dest'

    outgoing_buffer.seek(0)
    first_line = outgoing_buffer.readline()
    size_data = json.loads(first_line.strip())
    unstream_dir(outgoing_buffer, size_data['zipfile'], dest_dir)

    # Assure the new file is the same permissions
    new_file_path = dest_dir / 'ordinary_file.txt'
    assert oct(new_file_path.stat().st_mode) == oct(old_file_path.stat().st_mode)
