# pylint: disable=W0621

import shutil

from pathlib import Path

import pytest

from ansible_runner import defaults


CONTAINER_RUNTIMES = (
    'docker',
    'podman',
)


@pytest.fixture(autouse=True)
def mock_env_user(monkeypatch):
    monkeypatch.setenv("ANSIBLE_DEVEL_WARNING", "False")


@pytest.fixture(autouse=True)
def change_save_path(tmp_path, mocker):
    mocker.patch.object(defaults, 'AUTO_CREATE_DIR', str(tmp_path))


# TODO: determine if we want to add docker / podman
# to zuul instances in order to run these tests
def pytest_generate_tests(metafunc):
    """If a test uses the custom marker ``test_all_runtimes``, generate marks
    for all supported container runtimes. The requires the test to accept
    and use the ``runtime`` argument.

    Based on examples from https://docs.pytest.org/en/latest/example/parametrize.html.
    """

    for mark in getattr(metafunc.function, 'pytestmark', []):
        if getattr(mark, 'name', '') == 'test_all_runtimes':
            args = tuple(
                pytest.param(
                    runtime,
                    marks=pytest.mark.skipif(
                        shutil.which(runtime) is None,
                        reason=f'{runtime} is not installed',
                    ),
                )
                for runtime in CONTAINER_RUNTIMES
            )
            metafunc.parametrize('runtime', args)
            break


@pytest.fixture
def project_fixtures(tmp_path):
    source = Path(__file__).parent / 'fixtures' / 'projects'
    dest = tmp_path / 'projects'
    shutil.copytree(source, dest)

    yield dest

    shutil.rmtree(dest, ignore_errors=True)
