import os
import pytest

from ansible_runner.interface import run, run_async


def test_run():
    r = run(module='debug', host_pattern='localhost')
    assert r.status == 'successful'


def test_run_async():
    thread, r = run_async(module='debug', host_pattern='localhost')
    thread.join()
    assert r.status == 'successful'


@pytest.fixture
def printenv_example(test_data_dir):
    private_data_dir = os.path.join(test_data_dir, 'printenv')
    # TODO: remove if main code can handle this for us
    # https://github.com/ansible/ansible-runner/issues/493
    # for now, necessary to prevent errors on re-run
    settings_file = os.path.join(private_data_dir, 'env', 'settings')
    if os.path.exists(settings_file):
        os.remove(settings_file)
    return private_data_dir


@pytest.mark.serial
def test_env_accuracy(request, printenv_example):
    os.environ['SET_BEFORE_TEST'] = 'MADE_UP_VALUE'

    def remove_test_env_var():
        if 'SET_BEFORE_TEST' in os.environ:
            del os.environ['SET_BEFORE_TEST']

    request.addfinalizer(remove_test_env_var)

    res = run(
        private_data_dir=printenv_example,
        project_dir='/tmp',
        playbook=None,
        inventory=None,
        envvars={'FROM_TEST': 'FOOBAR'},
    )
    assert res.rc == 0, res.stdout.read()

    printenv_out = res.stdout.read()
    actual_env = {}
    for line in printenv_out.split('\n'):
        if not line:
            continue
        k, v = line.split('=', 1)
        actual_env[k] = v

    assert actual_env

    assert actual_env == res.config.env, printenv_out

    assert '/tmp' == res.config.cwd


@pytest.mark.serial
def test_env_accuracy_inside_container(request, printenv_example, container_runtime_installed):
    os.environ['SET_BEFORE_TEST'] = 'MADE_UP_VALUE'

    def remove_test_env_var():
        if 'SET_BEFORE_TEST' in os.environ:
            del os.environ['SET_BEFORE_TEST']

    request.addfinalizer(remove_test_env_var)

    res = run(
        private_data_dir=printenv_example,
        project_dir='/tmp',
        playbook=None,
        inventory=None,
        envvars={'FROM_TEST': 'FOOBAR'},
        settings={
            'process_isolation_executable': container_runtime_installed,
            'process_isolation': True
        }
    )
    assert res.rc == 0, res.stdout.read()

    printenv_out = res.stdout.read()
    actual_env = {}
    for line in printenv_out.split('\n'):
        if not line:
            continue
        k, v = line.split('=', 1)
        actual_env[k] = v

    expected_env = res.config.env.copy()

    # NOTE: the reported environment for containerized jobs will not account for
    # all environment variables, particularly those set by the entrypoint script
    for key, value in expected_env.items():
        assert key in actual_env
        assert actual_env[key] == value

    assert '/tmp' == res.config.cwd
