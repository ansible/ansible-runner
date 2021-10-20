# -*- coding: utf-8 -*-
import os
import signal
import sys

from uuid import uuid4

import pytest

from test.utils.common import iterate_timeout


@pytest.mark.test_all_runtimes
def test_module_run(cli, test_data_dir, runtime):
    r = cli([
        'run',
        '--process-isolation-executable', runtime,
        '-m', 'ping',
        '--hosts', 'testhost',
        test_data_dir.joinpath('containerized').as_posix(),
    ])

    assert '"ping": "pong"' in r.stdout


@pytest.mark.test_all_runtimes
def test_playbook_run(cli, test_data_dir, runtime):
    r = cli([
        'run',
        '--process-isolation-executable', runtime,
        '-p', 'test-container.yml',
        test_data_dir.joinpath('containerized').as_posix(),
    ])
    assert 'PLAY RECAP *******' in r.stdout
    assert 'failed=0' in r.stdout


@pytest.mark.test_all_runtimes
def test_provide_env_var(cli, test_data_dir, runtime):
    r = cli([
        'run',
        '--process-isolation-executable', runtime,
        '-p', 'printenv.yml',
        test_data_dir.joinpath('job_env').as_posix(),
    ])
    assert 'gifmyvqok2' in r.stdout, r.stdout


@pytest.mark.test_all_runtimes
@pytest.mark.skipif(sys.platform == 'darwin', reason='ansible-runner start does not work reliably on macOS')
def test_cli_kill_cleanup(cli, runtime, test_data_dir):
    unique_string = str(uuid4()).replace('-', '')
    ident = f'kill_test_{unique_string}'
    pdd = os.path.join(test_data_dir, 'sleep')
    cli_args = [
        'start', pdd,
        '-p', 'sleep.yml',
        '--ident', ident,
        '--process-isolation',
        '--process-isolation-executable', runtime,
    ]
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
