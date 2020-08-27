import pytest
from distutils.version import LooseVersion
import pkg_resources
import os


@pytest.fixture(autouse=True)
def mock_env_user(monkeypatch):
    monkeypatch.setenv("ANSIBLE_DEVEL_WARNING", "False")


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


@pytest.fixture
def test_data_dir():
    return os.path.join(os.path.dirname(__file__), 'data')
