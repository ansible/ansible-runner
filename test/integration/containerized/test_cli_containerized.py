# -*- coding: utf-8 -*-
import pytest


@pytest.mark.test_all_runtimes
def test_module_run(cli, project_fixtures, runtime):
    r = cli([
        'run',
        '--process-isolation-executable', runtime,
        '-m', 'ping',
        '--hosts', 'testhost',
        project_fixtures.joinpath('containerized').as_posix(),
    ])

    assert '"ping": "pong"' in r.stdout


@pytest.mark.test_all_runtimes
def test_playbook_run(cli, project_fixtures, runtime):
    # Ensure the container environment variable is set so that Ansible fact gathering
    # is able to detect it is running inside a container.
    envvars_path = project_fixtures / 'containerized' / 'env' / 'envvars'
    with envvars_path.open('a') as f:
        f.write(f'container: {runtime}\n')

    r = cli([
        'run',
        '--process-isolation-executable', runtime,
        '-p', 'test-container.yml',
        project_fixtures.joinpath('containerized').as_posix(),
    ])
    assert 'PLAY RECAP *******' in r.stdout
    assert 'failed=0' in r.stdout


@pytest.mark.test_all_runtimes
def test_provide_env_var(cli, project_fixtures, runtime):
    r = cli([
        'run',
        '--process-isolation-executable', runtime,
        '-p', 'printenv.yml',
        project_fixtures.joinpath('job_env').as_posix(),
    ])
    assert 'gifmyvqok2' in r.stdout, r.stdout
