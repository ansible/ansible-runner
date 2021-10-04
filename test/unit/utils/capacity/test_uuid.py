import pytest

from ansible_runner.utils.capacity import (
    _set_uuid,
    ensure_uuid,
)


@pytest.fixture
def mock_uuid(mocker):
    uuid = 'f6bf3d15-7a6b-480a-b29c-eb4d0acf38ce'
    mocker.patch('ansible_runner.utils.capacity.uuid.uuid4', return_value=uuid)

    return uuid


def test_set_uuid(mock_uuid, tmp_path):
    uuid_path = tmp_path / 'uuid'
    uuid = _set_uuid(uuid_path)

    assert uuid == mock_uuid
    assert uuid_path.exists()
    assert uuid_path.read_text() == mock_uuid


def test_set_uuid_bad_path(mock_uuid, tmp_path):
    uuid_path = tmp_path / 'nope' / 'uuid'
    with pytest.raises(FileNotFoundError, match='No such file or directory'):
        _set_uuid(uuid_path)


def test_ensure_uuid_does_not_exist(mocker, mock_uuid, tmp_path):
    mock_set_uuid = mocker.patch('ansible_runner.utils.capacity._set_uuid', return_value=mock_uuid)

    uuid_path = tmp_path / 'uuid'
    uuid = ensure_uuid(uuid_path)

    assert uuid == mock_uuid
    assert mock_set_uuid.call_count == 1


def test_ensure_uuid_exists(mocker, mock_uuid, tmp_path):
    mock_set_uuid = mocker.patch('ansible_runner.utils.capacity._set_uuid', return_value=mock_uuid)
    uuid_path = tmp_path / 'uuid'
    uuid_path.write_text(mock_uuid + '\n')

    uuid = ensure_uuid(uuid_path)

    assert uuid == mock_uuid
    assert mock_set_uuid.call_count == 0
