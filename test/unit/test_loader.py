from io import BytesIO

from pytest import raises, fixture
from six import string_types

import ansible_runner.loader

from ansible_runner.exceptions import ConfigurationError


@fixture
def loader(tmp_path):
    return ansible_runner.loader.ArtifactLoader(str(tmp_path))


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


def test_abspath(loader, tmp_path):
    res = loader.abspath('/test')
    assert res == '/test'

    res = loader.abspath('test')
    assert res == tmp_path.joinpath('test').as_posix()

    res = loader.abspath('~/test')
    assert res.startswith('/')


def test_load_file_text_cache_hit(loader, mocker, tmp_path):
    mock_get_contents = mocker.patch.object(ansible_runner.loader.ArtifactLoader, 'get_contents')
    mock_get_contents.return_value = 'test\nstring'

    assert not loader._cache

    testfile = tmp_path.joinpath('test').as_posix()

    # cache miss
    res = loader.load_file(testfile, string_types)
    assert mock_get_contents.called
    assert mock_get_contents.called_with_args(testfile)
    assert res == b'test\nstring'
    assert testfile in loader._cache

    mock_get_contents.reset_mock()

    # cache hit
    res = loader.load_file(testfile, string_types)
    assert not mock_get_contents.called
    assert res == b'test\nstring'
    assert testfile in loader._cache


def test_load_file_json(loader, mocker, tmp_path):
    mock_get_contents = mocker.patch.object(ansible_runner.loader.ArtifactLoader, 'get_contents')
    mock_get_contents.return_value = '---\ntest: string'

    assert not loader._cache

    testfile = tmp_path.joinpath('test').as_posix()
    res = loader.load_file(testfile)

    assert mock_get_contents.called
    assert mock_get_contents.called_with_args(testfile)
    assert testfile in loader._cache
    assert res['test'] == 'string'


def test_load_file_type_check(loader, mocker, tmp_path):
    mock_get_contents = mocker.patch.object(ansible_runner.loader.ArtifactLoader, 'get_contents')
    mock_get_contents.return_value = '---\ntest: string'

    assert not loader._cache

    testfile = tmp_path.joinpath('test').as_posix()

    # type check passes
    res = loader.load_file(testfile, dict)
    assert res is not None

    mock_get_contents.reset_mock()
    mock_get_contents.return_value = 'test string'

    loader._cache = {}

    # type check fails
    with raises(ConfigurationError):
        res = loader.load_file(testfile, dict)
        assert res is not None


def test_get_contents_ok(loader, mocker):
    mock_open = mocker.patch('codecs.open')

    handler = BytesIO()
    handler.write(b"test string")
    handler.seek(0)

    mock_open.return_value.__enter__.return_value = handler

    res = loader.get_contents('/tmp')
    assert res == b'test string'


def test_get_contents_invalid_path(loader, tmp_path):
    with raises(ConfigurationError):
        loader.get_contents(tmp_path.joinpath('invalid').as_posix())


def test_get_contents_exception(loader, tmp_path):
    with raises(ConfigurationError):
        loader.get_contents(tmp_path.as_posix())
