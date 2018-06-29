from io import BytesIO

from pytest import raises, fixture
from mock import patch
from six import string_types

import ansible_runner.loader

from ansible_runner.exceptions import ConfigurationError


@fixture
def loader():
    return ansible_runner.loader.ArtifactLoader('/tmp')


def test__load_json_success(loader):
    res = loader._load_json('{"test": "string"}')
    assert isinstance(res, dict)
    assert res['test'] == 'string'


def test__load_json_failure(loader):
    res = loader._load_json('---\ntest: string')
    assert res is None

    res = loader._load_json('test string')
    assert res is None


def test__load_yaml_success(loader):
    res = loader._load_yaml('---\ntest: string')
    assert isinstance(res, dict)
    assert res['test'] == 'string'

    res = loader._load_yaml('{"test": "string"}')
    assert isinstance(res, dict)
    assert res['test'] == 'string'


def test__load_yaml_failure(loader):
    res = loader._load_yaml('---\ntest: string:')
    assert res is None


def test_abspath(loader):
    res = loader.abspath('/test')
    assert res == '/test'

    res = loader.abspath('test')
    assert res == '/tmp/test'

    res = loader.abspath('~/test')
    assert res.startswith('/')


def test_load_file_text(loader):
    with patch.object(ansible_runner.loader.ArtifactLoader, 'get_contents') as mock_get_contents:
        mock_get_contents.return_value = 'test\nstring'

        assert not loader._cache

        # cache miss
        res = loader.load_file('/tmp/test', string_types)
        assert mock_get_contents.called
        assert mock_get_contents.called_with_args('/tmp/test')
        assert res == b'test\nstring'
        assert '/tmp/test' in loader._cache

        mock_get_contents.reset_mock()

        # cache hit
        res = loader.load_file('/tmp/test', string_types)
        assert not mock_get_contents.called
        assert res == b'test\nstring'
        assert '/tmp/test' in loader._cache


def test_load_file_json(loader):
    with patch.object(ansible_runner.loader.ArtifactLoader, 'get_contents') as mock_get_contents:
        mock_get_contents.return_value = '---\ntest: string'

        assert not loader._cache

        res = loader.load_file('/tmp/test')

        assert mock_get_contents.called
        assert mock_get_contents.called_with_args('/tmp/test')
        assert '/tmp/test' in loader._cache
        assert res['test'] == 'string'


def test_load_file_type_check(loader):
    with patch.object(ansible_runner.loader.ArtifactLoader, 'get_contents') as mock_get_contents:
        mock_get_contents.return_value = '---\ntest: string'

        assert not loader._cache

        # type check passes
        res = loader.load_file('/tmp/test', dict)
        assert res is not None

        mock_get_contents.reset_mock()
        mock_get_contents.return_value = 'test string'

        loader._cache = {}

        # type check fails
        with raises(ConfigurationError):
            res = loader.load_file('/tmp/test', dict)
            assert res is not None


def test_get_contents_ok(loader):
    with patch('ansible_runner.loader.open') as mock_open:
        handler = BytesIO()
        handler.write(b"test string")
        handler.seek(0)

        mock_open.return_value.__enter__.return_value  = handler

        res = loader.get_contents('/tmp')
        assert res == b'test string'


def test_get_contents_invalid_path(loader):
    with raises(ConfigurationError):
        loader.get_contents('/tmp/invalid')


def test_get_contents_exception(loader):
    with raises(ConfigurationError):
        loader.get_contents('/tmp')
