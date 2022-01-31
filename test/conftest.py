import shutil

from distutils.version import LooseVersion
from pathlib import Path

from ansible_runner import defaults

import pkg_resources
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
def is_pre_ansible28():
    try:
        if LooseVersion(pkg_resources.get_distribution('ansible').version) < LooseVersion('2.8'):
            return True
    except pkg_resources.DistributionNotFound:
        # ansible-base (e.g. ansible 2.10 and beyond) is not accessible in this way
        pass


@pytest.fixture(scope='session')
def skipif_pre_ansible28(is_pre_ansible28):
    if is_pre_ansible28:
        pytest.skip("Valid only on Ansible 2.8+")


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
