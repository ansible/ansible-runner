# -*- coding: utf-8 -*-
import os

import pytest

HERE = os.path.abspath(os.path.dirname(__file__))


def test_module_run(cli, container_runtime_available):
    if not container_runtime_available:
        pytest.skip('container runtime(s) not available')
    cli(['-m', 'ping','--hosts', 'localhost', 'run', os.path.join(HERE, 'priv_data')])


def test_playbook_run(cli, container_runtime_available):
    if not container_runtime_available:
        pytest.skip('container runtime(s) not available')
    cli(['run', os.path.join(HERE,'priv_data'), '-p', 'test-container.yml'])
