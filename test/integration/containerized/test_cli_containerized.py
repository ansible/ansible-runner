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
    r = cli(['run', '-m', 'ping', '--hosts', 'localhost', os.path.join(HERE, 'priv_data')])
    assert '"ping": "pong"' in r.stdout


@pytest.mark.serial
def test_playbook_run(cli, skip_if_no_podman):
    r = cli(['run', os.path.join(HERE, 'priv_data'), '-p', 'test-container.yml'])
    assert 'PLAY RECAP *******' in r.stdout
    assert 'failed=0' in r.stdout


@pytest.mark.serial
def test_provide_env_var(cli, skip_if_no_podman, test_data_dir):
    r = cli(['run', os.path.join(test_data_dir, 'job_env'), '-p', 'printenv.yml'])
    assert 'gifmyvqok2' in r.stdout, r.stdout
