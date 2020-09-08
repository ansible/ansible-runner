import os
import pytest
import shutil

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
    env_dir = os.path.join(private_data_dir, 'env')
    if os.path.exists(env_dir):
        shutil.rmtree(env_dir)
    return private_data_dir


def get_env_data(res):
    for event in res.events:
        found = bool(
            event['event'] == 'runner_on_ok' and event.get(
                'event_data', {}
            ).get('task_action', None) == 'look_at_environment'
        )
        if found:
            return event['event_data']['res']
    else:
        print('output:')
        print(res.stdout.read())
        raise RuntimeError('Count not find look_at_environment task from playbook')


@pytest.mark.serial
def test_env_accuracy(request, printenv_example):
    os.environ['SET_BEFORE_TEST'] = 'MADE_UP_VALUE'

    def remove_test_env_var():
        if 'SET_BEFORE_TEST' in os.environ:
            del os.environ['SET_BEFORE_TEST']

    request.addfinalizer(remove_test_env_var)

    res = run(
        private_data_dir=printenv_example,
        playbook='get_environment.yml',
        inventory=None,
        envvars={'FROM_TEST': 'FOOBAR'},
    )
    assert res.rc == 0, res.stdout.read()

    actual_env = get_env_data(res)['environment']

    assert actual_env == res.config.env


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
        playbook='get_environment.yml',
        inventory=None,
        envvars={'FROM_TEST': 'FOOBAR'},
        settings={
            'process_isolation_executable': container_runtime_installed,
            'process_isolation': True
        }
    )
    assert res.rc == 0, res.stdout.read()

    actual_env = get_env_data(res)['environment']

    expected_env = res.config.env.copy()

    # NOTE: the reported environment for containerized jobs will not account for
    # all environment variables, particularly those set by the entrypoint script
    for key, value in expected_env.items():
        assert key in actual_env
        assert actual_env[key] == value, 'Reported value wrong for {0} env var'.format(key)

    assert '/tmp' == res.config.cwd
