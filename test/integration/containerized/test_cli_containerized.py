# -*- coding: utf-8 -*-
import os
import shutil
import signal
import sys

from uuid import uuid4

import pytest

from test.utils.common import iterate_timeout

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
@pytest.mark.skipif(sys.platform == 'darwin', reason='ansible-runner start does not work reliably on macOS')
@pytest.mark.parametrize('runtime', ['podman', 'docker'])
def test_cli_kill_cleanup(cli, runtime, test_data_dir):
    if shutil.which(runtime) is None:
        pytest.skip(f'{runtime} is unavailable')

    unique_string = str(uuid4()).replace('-', '')
    ident = f'kill_test_{unique_string}'
    pdd = os.path.join(test_data_dir, 'sleep')
    cli_args = ['start', pdd, '-p', 'sleep.yml', '--ident', ident,
                '--process-isolation', '--process-isolation-executable', runtime]
    cli(cli_args)

    def container_is_running():
        r = cli([runtime, 'ps', '-f', f'name=ansible_runner_{ident}', '--format={{.Names}}'], bare=True)
        return ident in r.stdout

    timeout = 10
    for _ in iterate_timeout(timeout, 'confirm ansible-runner started container', interval=1):
        if container_is_running():
            break

    # Here, we will do sigterm to kill the parent process, it should handle this gracefully
    with open(os.path.join(pdd, 'pid'), 'r') as f:
        pid = int(f.read().strip())
    os.kill(pid, signal.SIGTERM)

    for _ in iterate_timeout(timeout, 'confirm container no longer running', interval=1):
        if not container_is_running():
            break
