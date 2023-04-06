import shutil

from pathlib import Path
from packaging.version import Version

from ansible_runner import defaults
from ansible_runner.utils.importlib_compat import importlib_metadata

import pytest


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


@pytest.fixture(scope='session')
def is_pre_ansible211():
    """
    Check if the version of Ansible is less than 2.11.

    CI tests with either ansible-core (>=2.11), ansible-base (==2.10), and ansible (<=2.9).
    """

    try:
        if importlib_metadata.version("ansible-core"):
            return False
    except importlib_metadata.PackageNotFoundError:
        # Must be ansible-base or ansible
        return True


@pytest.fixture(scope='session')
def skipif_pre_ansible211(is_pre_ansible211):
    if is_pre_ansible211:
        pytest.skip("Valid only on Ansible 2.11+")


@pytest.fixture(scope="session")
def is_pre_ansible212():
    try:
        base_version = importlib_metadata.version("ansible")
        if Version(base_version) < Version("2.12"):
            return True
    except importlib_metadata.PackageNotFoundError:
        pass


@pytest.fixture(scope="session")
def skipif_pre_ansible212(is_pre_ansible212):
    if is_pre_ansible212:
        pytest.skip("Valid only on Ansible 2.12+")


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
