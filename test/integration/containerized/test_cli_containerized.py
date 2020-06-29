# -*- coding: utf-8 -*-
import os

import pytest

HERE = os.path.abspath(os.path.dirname(__file__))


# TODO: determine if we want to add docker / podman
# to zuul instances in order to run these tests
@pytest.fixture(scope="session", autouse=True)
def container_runtime_available():
    import subprocess
    import warnings

    runtimes_available = True
    for runtime in ('docker', 'podman'):
        try:
            subprocess.run([runtime, '-v'])
        except FileNotFoundError:
            warnings.warn(UserWarning(f"{runtime} not available"))
            runtimes_available = False
    return runtimes_available


def test_module_run(cli, container_runtime_available):
    if not container_runtime_available:
        pytest.skip('container runtime(s) not available')
    cli(['-m', 'ping','--hosts', 'localhost', 'run', os.path.join(HERE, 'priv_data')])


def test_playbook_run(cli, container_runtime_available):
    if not container_runtime_available:
        pytest.skip('container runtime(s) not available')
    cli(['run', os.path.join(HERE,'priv_data'), '-p', 'test-container.yml'])
