# -*- coding: utf-8 -*-
import os

import pytest

HERE = os.path.abspath(os.path.dirname(__file__))


@pytest.mark.serial
def test_module_run(cli, container_runtime_available):
    if not container_runtime_available:
        pytest.skip('container runtime(s) not available')
    cli(['-m', 'ping','--hosts', 'localhost', 'run', os.path.join(HERE, 'priv_data')])


@pytest.mark.serial
def test_playbook_run(cli, container_runtime_available):
    if not container_runtime_available:
        pytest.skip('container runtime(s) not available')
    cli(['run', os.path.join(HERE,'priv_data'), '-p', 'test-container.yml'])


@pytest.mark.serial
def test_adhoc_localhost_setup(cli, container_runtime_available, container_runtime_installed):
    if not container_runtime_available:
        pytest.skip('container runtime(s) not available')
    cli(
        [
            'adhoc',
            '--private-data-dir', os.path.join(HERE,'priv_data'),
            '--container-runtime', container_runtime_installed,
            'localhost', '-m', 'setup'
        ]
    )


@pytest.mark.serial
def test_playbook_with_private_data_dir(cli, container_runtime_available, container_runtime_installed):
    if not container_runtime_available:
        pytest.skip('container runtime(s) not available')
    cli(
        [
            'playbook',
            '--private-data-dir', os.path.join(HERE,'priv_data'),
            '--container-runtime', container_runtime_installed,
            'test-container.yml'
        ]
    )
