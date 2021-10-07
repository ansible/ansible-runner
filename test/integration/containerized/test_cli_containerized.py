# -*- coding: utf-8 -*-
import os
import signal
import time

from uuid import uuid4

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


@pytest.mark.serial
def test_cli_kill_cleanup(cli, test_data_dir, container_runtime_installed):
    unique_string = str(uuid4()).replace('-', '')
    ident = f'kill_test_{unique_string}'
    pdd = os.path.join(test_data_dir, 'sleep')
    cli_args = ['start', pdd, '-p', 'sleep.yml', '--ident', ident,
                '--process-isolation', '--process-isolation-executable', container_runtime_installed]
    cli(cli_args)

    def container_is_running():
        r = cli([container_runtime_installed, 'ps', '-f', f'name=ansible_runner_{ident}', '--format={{.Names}}'], bare=True)
        return ident in r.stdout

    tries = 5
    for i in range(tries):
        if container_is_running():
            break
        time.sleep(1)
    else:
        assert container_is_running()

    # give playbook execution time to start
    time.sleep(5)

    # Here, we will do sigterm to kill the parent process, it should handle this gracefully
    with open(os.path.join(pdd, 'pid'), 'r') as f:
        pid = int(f.read().strip())
    os.kill(pid, signal.SIGTERM)

    for i in range(tries):
        if not container_is_running():
            break  # yay, test passed
        time.sleep(1)
    else:
        assert not container_is_running()
