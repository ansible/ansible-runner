import os
import pytest
import shutil

from ansible_runner import defaults
from ansible_runner.interface import run, run_async, run_command, run_command_async, get_plugin_docs, \
    get_plugin_docs_async, get_plugin_list, get_ansible_config, get_inventory


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

    env_data = get_env_data(res)
    actual_env = env_data['environment']

    expected_env = res.config.env.copy()

    # NOTE: the reported environment for containerized jobs will not account for
    # all environment variables, particularly those set by the entrypoint script
    for key, value in expected_env.items():
        assert key in actual_env
        assert actual_env[key] == value, 'Reported value wrong for {0} env var'.format(key)

    assert env_data['cwd'] == res.config.cwd


def test_multiple_inventories(test_data_dir):
    private_data_dir = os.path.join(test_data_dir, 'debug')

    res = run(
        private_data_dir=private_data_dir,
        playbook='debug.yml',
    )
    stdout = res.stdout.read()
    assert res.rc == 0, stdout

    # providing no inventory should cause <private_data_dir>/inventory
    # to be used, reading both inventories in the directory
    assert 'host_1' in stdout
    assert 'host_2' in stdout


def test_inventory_absolute_path(test_data_dir):
    private_data_dir = os.path.join(test_data_dir, 'debug')

    res = run(
        private_data_dir=private_data_dir,
        playbook='debug.yml',
        inventory=[
            os.path.join(private_data_dir, 'inventory', 'inv_1'),
        ],
    )
    stdout = res.stdout.read()
    assert res.rc == 0, stdout

    # hosts can be down-selected to one inventory out of those available
    assert 'host_1' in stdout
    assert 'host_2' not in stdout


def test_run_command(test_data_dir):
    private_data_dir = os.path.join(test_data_dir, 'debug')
    inventory = os.path.join(private_data_dir, 'inventory', 'inv_1')
    playbook = os.path.join(private_data_dir, 'project', 'debug.yml')
    out, err, rc = run_command(
        private_data_dir=private_data_dir,
        executable_cmd='ansible-playbook',
        cmdline_args=[playbook, '-i', inventory]
    )
    assert "Hello world!" in out
    assert rc == 0
    assert err == ''


def test_run_ansible_command_within_container(test_data_dir, container_runtime_installed):
    private_data_dir = os.path.join(test_data_dir, 'debug')
    inventory = os.path.join(private_data_dir, 'inventory', 'inv_1')
    playbook = os.path.join(private_data_dir, 'project', 'debug.yml')
    container_kwargs = {
        'process_isolation_executable': container_runtime_installed,
        'process_isolation': True,
        'container_image': defaults.default_container_image
    }
    rc, out, err = run_command(
        private_data_dir=private_data_dir,
        executable_cmd='ansible-playbook',
        cmdline_args=[playbook, '-i', inventory],
        **container_kwargs
    )
    assert "Hello world!" in out
    assert rc == 0
    assert err == ''


def test_run_script_within_container(test_data_dir, container_runtime_installed):
    private_data_dir = os.path.join(test_data_dir, 'debug')
    script_path = os.path.join(test_data_dir, 'files')
    container_volume_mounts = ["{}:{}:Z".format(script_path, script_path)]
    container_kwargs = {
        'process_isolation_executable': container_runtime_installed,
        'process_isolation': True,
        'container_image': defaults.default_container_image,
        'container_volume_mounts': container_volume_mounts
    }
    out, _, rc = run_command(
        private_data_dir=private_data_dir,
        executable_cmd='python3',
        cmdline_args=[os.path.join(script_path, 'test_ee.py')],
        **container_kwargs
    )

    assert "os-release" in out
    assert rc == 0


def test_run_command_async(test_data_dir):
    private_data_dir = os.path.join(test_data_dir, 'debug')
    inventory = os.path.join(private_data_dir, 'inventory', 'inv_1')
    playbook = os.path.join(private_data_dir, 'project', 'debug.yml')
    thread, r = run_command_async(
        private_data_dir=private_data_dir,
        executable_cmd='ansible-playbook',
        cmdline_args=[playbook, '-i', inventory]
    )
    thread.join()
    out = r.stdout.read()
    assert "Hello world!" in out
    assert r.status == 'successful'


def test_get_plugin_docs():
    out, _ = get_plugin_docs(
        plugin_names=['file', 'copy'],
        plugin_type='module',
        quiet=True
    )
    assert 'copy' in out
    assert 'file' in out


def test_get_plugin_docs_async():
    thread, r = get_plugin_docs_async(
        plugin_names=['file', 'copy'],
        plugin_type='module',
        quiet=True
    )
    thread.join()
    out = r.stdout.read()
    assert 'copy' in out
    assert 'file' in out
    assert r.status == 'successful'


def test_get_plugin_docs_within_container(container_runtime_installed):
    container_kwargs = {
        'process_isolation_executable': container_runtime_installed,
        'process_isolation': True,
        'container_image': defaults.default_container_image
    }
    out, _ = get_plugin_docs(
        plugin_names=['file', 'copy'],
        plugin_type='module',
        quiet=True,
        **container_kwargs
    )
    assert 'copy' in out
    assert 'file' in out


def test_get_plugin_docs_list():
    out, _ = get_plugin_list(
        list_files=True,
        quiet=True
    )
    assert 'copy' in out
    assert 'file' in out


def test_get_plugin_docs_list_within_container(container_runtime_installed):
    container_kwargs = {
        'process_isolation_executable': container_runtime_installed,
        'process_isolation': True,
        'container_image': defaults.default_container_image
    }
    out, _ = get_plugin_list(
        list_files=True,
        quiet=True,
        **container_kwargs
    )
    assert 'copy' in out
    assert 'file' in out


def test_ansible_config():
    out, _ = get_ansible_config(
        action='list',
        quiet=True
    )
    assert 'DEFAULT_VERBOSITY' in out


def test_get_inventory(test_data_dir):
    private_data_dir = os.path.join(test_data_dir, 'debug')
    inventory1 = os.path.join(private_data_dir, 'inventory', 'inv_1')
    inventory2 = os.path.join(private_data_dir, 'inventory', 'inv_2')

    out, _ = get_inventory(
        action='list',
        inventories=[inventory1, inventory2],
        response_format='json',
        quiet=True
    )
    assert 'host_1' in out['ungrouped']['hosts']
    assert 'host_2' in out['ungrouped']['hosts']


def test_get_inventory_within_container(test_data_dir, container_runtime_installed):
    container_kwargs = {
        'process_isolation_executable': container_runtime_installed,
        'process_isolation': True,
        'container_image': defaults.default_container_image
    }
    private_data_dir = os.path.join(test_data_dir, 'debug')
    inventory1 = os.path.join(private_data_dir, 'inventory', 'inv_1')
    inventory2 = os.path.join(private_data_dir, 'inventory', 'inv_2')

    out, _ = get_inventory(
        action='list',
        inventories=[inventory1, inventory2],
        response_format='json',
        quiet=True,
        **container_kwargs
    )
    assert 'host_1' in out['ungrouped']['hosts']
    assert 'host_2' in out['ungrouped']['hosts']
