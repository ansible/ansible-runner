import pytest

from ansible_runner.config.runner import RunnerConfig
from ansible_runner._internal._dump_artifacts import dump_artifacts


@pytest.mark.parametrize(
    'playbook', (
        [{'playbook': [{'hosts': 'all'}]}],
        {'playbook': [{'hosts': 'all'}]},
    )
)
def test_dump_artifacts_playbook_object(mocker, playbook):
    mock_dump_artifact = mocker.patch('ansible_runner._internal._dump_artifacts.dump_artifact', side_effect=AttributeError('Raised intentionally'))
    mocker.patch('ansible_runner.utils.isplaybook', return_value=True)

    playbook_string = '[{"playbook": [{"hosts": "all"}]}]'
    kwargs = {'private_data_dir': '/tmp', 'playbook': playbook}

    with pytest.raises(AttributeError, match='Raised intentionally'):
        dump_artifacts(RunnerConfig(**kwargs))

    mock_dump_artifact.assert_called_once_with(playbook_string, '/tmp/project', 'main.json')


def test_dump_artifacts_role(mocker):
    mock_dump_artifact = mocker.patch('ansible_runner._internal._dump_artifacts.dump_artifact')

    kwargs = {
        'private_data_dir': '/tmp',
        'role': 'test',
        'playbook': [{'playbook': [{'hosts': 'all'}]}],
    }

    dump_artifacts(RunnerConfig(**kwargs))

    assert mock_dump_artifact.call_count == 2
    mock_dump_artifact.assert_called_with('{"ANSIBLE_ROLES_PATH": "/tmp/roles"}', '/tmp/env', 'envvars')


def test_dump_artifacts_roles_path(mocker):
    mock_dump_artifact = mocker.patch('ansible_runner._internal._dump_artifacts.dump_artifact')

    kwargs = {
        'private_data_dir': '/tmp',
        'role': 'test',
        'roles_path': '/tmp/altrole',
        'playbook': [{'playbook': [{'hosts': 'all'}]}],
    }

    dump_artifacts(RunnerConfig(**kwargs))

    assert mock_dump_artifact.call_count == 2
    mock_dump_artifact.assert_called_with('{"ANSIBLE_ROLES_PATH": "/tmp/altrole:/tmp/roles"}', '/tmp/env', 'envvars')


def test_dump_artifacts_role_vars(mocker):
    mock_dump_artifact = mocker.patch('ansible_runner._internal._dump_artifacts.dump_artifact', side_effect=AttributeError('Raised intentionally'))

    kwargs = {
        'private_data_dir': '/tmp',
        'role': 'test',
        'role_vars': {'name': 'nginx'},
        'playbook': [{'playbook': [{'hosts': 'all'}]}],
    }

    with pytest.raises(AttributeError, match='Raised intentionally'):
        dump_artifacts(RunnerConfig(**kwargs))

    mock_dump_artifact.assert_called_once_with(
        '[{"hosts": "all", "roles": [{"name": "test", "vars": {"name": "nginx"}}]}]',
        '/tmp/project',
        'main.json'
    )


def test_dump_artifacts_role_skip_facts(mocker):
    mock_dump_artifact = mocker.patch('ansible_runner._internal._dump_artifacts.dump_artifact', side_effect=AttributeError('Raised intentionally'))

    kwargs = {
        'private_data_dir': '/tmp',
        'role': 'test',
        'role_skip_facts': {'name': 'nginx'},
        'playbook': [{'playbook': [{'hosts': 'all'}]}],
    }

    with pytest.raises(AttributeError, match='Raised intentionally'):
        dump_artifacts(RunnerConfig(**kwargs))

    mock_dump_artifact.assert_called_once_with(
        '[{"hosts": "all", "roles": [{"name": "test"}], "gather_facts": false}]',
        '/tmp/project',
        'main.json'
    )


def test_dump_artifacts_inventory_string(mocker):
    mock_dump_artifact = mocker.patch('ansible_runner._internal._dump_artifacts.dump_artifact')

    inv = '[all]\nlocalhost'
    kwargs = {'private_data_dir': '/tmp', 'inventory': inv}
    dump_artifacts(RunnerConfig(**kwargs))

    mock_dump_artifact.assert_called_once_with(inv, '/tmp/inventory', 'hosts')


def test_dump_artifacts_inventory_path(mocker):
    mock_dump_artifact = mocker.patch('ansible_runner._internal._dump_artifacts.dump_artifact')

    inv = '/tmp'
    kwargs = {'private_data_dir': '/tmp', 'inventory': inv}
    dump_artifacts(RunnerConfig(**kwargs))

    assert mock_dump_artifact.call_count == 0
    assert mock_dump_artifact.called is False
    assert kwargs['inventory'] == inv


def test_dump_artifacts_inventory_object(mocker):
    mock_dump_artifact = mocker.patch('ansible_runner._internal._dump_artifacts.dump_artifact')

    inv = {'foo': 'bar'}
    inv_string = '{"foo": "bar"}'
    kwargs = {'private_data_dir': '/tmp', 'inventory': inv}
    dump_artifacts(RunnerConfig(**kwargs))

    mock_dump_artifact.assert_called_once_with(inv_string, '/tmp/inventory', 'hosts.json')


def test_dump_artifacts_inventory_string_path(mocker):
    mocker.patch('ansible_runner.utils.os.path.exists', return_value=True)

    inv_string = 'site1'
    kwargs = {'private_data_dir': '/tmp', 'inventory': inv_string}
    rc = RunnerConfig(**kwargs)
    dump_artifacts(rc)

    assert rc.inventory == '/tmp/inventory/site1'


def test_dump_artifacts_inventory_string_abs_path(mocker):
    mocker.patch('ansible_runner.utils.os.path.exists', return_value=True)

    inv_string = '/tmp/site1'
    kwargs = {'private_data_dir': '/tmp', 'inventory': inv_string}
    rc = RunnerConfig(**kwargs)
    dump_artifacts(rc)

    assert rc.inventory == '/tmp/site1'


def test_dump_artifacts_passwords(mocker):
    mock_dump_artifact = mocker.patch('ansible_runner._internal._dump_artifacts.dump_artifact')

    kwargs = {
        'private_data_dir': '/tmp',
        'passwords': {"a": "b"},
        'envvars': {"abc": "def"},
        'ssh_key': 'asdfg1234',
    }

    dump_artifacts(RunnerConfig(**kwargs))

    assert mock_dump_artifact.call_count == 3
    mock_dump_artifact.assert_any_call('{"a": "b"}', '/tmp/env', 'passwords')
    mock_dump_artifact.assert_any_call('{"abc": "def"}', '/tmp/env', 'envvars')
    mock_dump_artifact.assert_called_with('asdfg1234', '/tmp/env', 'ssh_key')


def test_dont_dump_artifacts_passwords(mocker):
    mock_dump_artifact = mocker.patch('ansible_runner._internal._dump_artifacts.dump_artifact')

    kwargs = {
        'private_data_dir': '/tmp',
        'passwords': {"a": "b"},
        'envvars': {"abd": "def"},
        'ssh_key': 'asdfg1234',
        'suppress_env_files': True
    }

    dump_artifacts(RunnerConfig(**kwargs))

    assert mock_dump_artifact.call_count == 0


@pytest.mark.parametrize(
    ('key', 'value', 'value_str'), (
        ('extravars', {'foo': 'bar'}, '{"foo": "bar"}'),
        ('passwords', {'foo': 'bar'}, '{"foo": "bar"}'),
        ('settings', {'foo': 'bar'}, '{"foo": "bar"}'),
        ('ssh_key', '1234567890', '1234567890'),
        ('cmdline', '--tags foo --skip-tags', '--tags foo --skip-tags'),
    )
)
def test_dump_artifacts_extra_keys(mocker, key, value, value_str):
    mock_dump_artifact = mocker.patch('ansible_runner._internal._dump_artifacts.dump_artifact')

    kwargs = {'private_data_dir': '/tmp'}
    kwargs.update({key: value})

    rc = RunnerConfig(**kwargs)
    dump_artifacts(rc)

    mock_dump_artifact.assert_called_once_with(value_str, '/tmp/env', key)
