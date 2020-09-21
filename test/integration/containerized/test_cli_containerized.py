# -*- coding: utf-8 -*-
import os

import pytest

HERE = os.path.abspath(os.path.dirname(__file__))


@pytest.fixture
def skip_if_no_podman(container_runtime_installed):
    if container_runtime_installed != 'podman':
        pytest.skip('podman container runtime(s) not available')


@pytest.mark.serial
def test_module_run(cli, skip_if_no_podman):
    r = cli(['run', '-m', 'ping','--hosts', 'localhost', os.path.join(HERE, 'priv_data')])
    assert '"ping": "pong"' in r.stdout


@pytest.mark.serial
def test_playbook_run(cli, skip_if_no_podman):
    r = cli(['run', os.path.join(HERE,'priv_data'), '-p', 'test-container.yml'])
    assert 'PLAY RECAP *******' in r.stdout
    assert 'failed=0' in r.stdout


@pytest.mark.serial
def test_provide_env_var(cli, skip_if_no_podman, test_data_dir):
    r = cli(['run', os.path.join(test_data_dir, 'job_env'), '-p', 'printenv.yml'])
    assert 'gifmyvqok2' in r.stdout, r.stdout


@pytest.mark.serial
def test_adhoc_localhost_setup(cli, skip_if_no_podman, container_runtime_installed):
    r = cli(
        [
            'adhoc',
            '--private-data-dir', os.path.join(HERE,'priv_data'),
            '--container-runtime', container_runtime_installed,
            'localhost', '-m', 'setup'
        ]
    )
    # TODO: look for some fact that indicates we are in container?
    assert '"ansible_facts": {' in r.stdout


@pytest.mark.serial
def test_playbook_with_private_data_dir(cli, skip_if_no_podman, container_runtime_installed):
    # tests using a private_data_dir in conjunction with an absolute path
    r = cli(
        [
            'playbook',
            '--private-data-dir', os.path.join(HERE,'priv_data'),
            '--container-runtime', container_runtime_installed,
            os.path.join(HERE, 'priv_data/project/test-container.yml')
        ]
    )
    assert 'PLAY RECAP *******' in r.stdout
    assert 'failed=0' in r.stdout


@pytest.mark.serial
def test_playbook_with_relative_path(cli, skip_if_no_podman, container_runtime_installed):
    r = cli(
        [
            'playbook',
            '--container-runtime', container_runtime_installed,
            'test/integration/containerized/priv_data/project/test-container.yml'
        ]
    )
    assert 'PLAY RECAP *******' in r.stdout
    assert 'failed=0' in r.stdout
