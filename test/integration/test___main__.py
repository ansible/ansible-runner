import os
import sys
import uuid
import json
import random
import string
import tempfile
import shutil

import pytest

from ansible_runner.__main__ import main


def random_string():
    return ''.join(random.choice(string.ascii_uppercase + string.digits)
                   for _ in range(random.randint(3, 20)))


def random_json(keys=None):
    data = dict()
    if keys:
        for key in keys:
            data[key] = random_string()
    else:
        for _ in range(0, 5):
            data[random_string()] = random_string()
    return json.dumps(data)


def cmdline(command, *args):
    cmdline = ['ansible-runner', command]
    cmdline.extend(args)
    sys.argv = cmdline


def test_main_bad_private_data_dir():
    tmpfile = os.path.join('/tmp', str(uuid.uuid4().hex))
    open(tmpfile, 'w').write(random_string())

    cmdline('run', tmpfile, '-p', 'fake')

    try:
        with pytest.raises(OSError):
            main()
    finally:
        os.remove(tmpfile)


def run_role(options, mocker, private_data_dir, expected_rc=0):
    args = ['run', private_data_dir]
    args.extend(options)
    mock_run = mocker.patch('ansible_runner.interface.run')
    with pytest.raises(SystemExit) as exc:
        main(args)

    assert exc.type == SystemExit
    assert exc.value.code == expected_rc

    return mock_run


def test_cmdline_role_defaults(mocker):
    """Run a role directly with all command line defaults
    """
    private_data_dir = tempfile.mkdtemp()
    options = ['-r', 'test']

    playbook = [{'hosts': 'all', 'gather_facts': True, 'roles': [{'role': 'test'}]}]

    run_options = {
        'private_data_dir': private_data_dir,
        'playbook': playbook
    }

    result = run_role(options, mocker, private_data_dir)
    result.called_with_args([run_options])


def test_cmdline_role_skip_facts(mocker):
    """Run a role directly and set --role-skip-facts option
    """
    private_data_dir = tempfile.mkdtemp()
    options = ['-r', 'test', '--role-skip-facts']

    playbook = [{'hosts': 'all', 'gather_facts': False, 'roles': [{'role': 'test'}]}]

    run_options = {
        'private_data_dir': private_data_dir,
        'playbook': playbook
    }

    result = run_role(options, mocker, private_data_dir)
    result.called_with_args([run_options])


def test_cmdline_role_inventory(mocker):
    """Run a role directly and set --inventory option
    """
    private_data_dir = tempfile.mkdtemp()
    options = ['-r', 'test', '--inventory hosts']

    playbook = [{'hosts': 'all', 'gather_facts': False, 'roles': [{'role': 'test'}]}]

    run_options = {
        'private_data_dir': private_data_dir,
        'playbook': playbook,
        'inventory': 'hosts'
    }

    result = run_role(options, mocker, private_data_dir)
    result.called_with_args([run_options])


def test_cmdline_role_vars(mocker):
    """Run a role directly and set --role-vars option
    """
    private_data_dir = tempfile.mkdtemp()
    options = ['-r', 'test', '--role-vars "foo=bar"']

    playbook = [{
        'hosts': 'all',
        'gather_facts': False,
        'roles': [{
            'role': 'test',
            'vars': {'foo': 'bar'}
        }]
    }]

    run_options = {
        'private_data_dir': private_data_dir,
        'playbook': playbook
    }

    result = run_role(options, mocker, private_data_dir)
    result.called_with_args([run_options])


def test_cmdline_roles_path(mocker):
    """Run a role directly and set --roles-path option
    """
    private_data_dir = tempfile.mkdtemp()
    options = ['-r', 'test', '--roles-path /tmp/roles']

    playbook = [{'hosts': 'all', 'gather_facts': False, 'roles': [{'role': 'test'}]}]

    run_options = {
        'private_data_dir': private_data_dir,
        'playbook': playbook,
        'envvars': {'ANSIBLE_ROLES_PATH': '/tmp/roles'}
    }

    result = run_role(options, mocker, private_data_dir)
    result.called_with_args([run_options])


def test_cmdline_role_with_playbook_option():
    """Test error is raised with invalid command line option '-p'
    """
    cmdline('run', 'private_data_dir', '-r', 'fake', '-p', 'fake')
    with pytest.raises(SystemExit) as exc:
        main()
        assert exc == 1


def test_cmdline_playbook(is_pre_ansible28):
    try:
        private_data_dir = tempfile.mkdtemp()
        play = [{'hosts': 'all', 'tasks': [{'debug': {'msg': random_string()}}]}]

        path = os.path.join(private_data_dir, 'project')
        os.makedirs(path)

        playbook = os.path.join(path, 'main.yaml')
        with open(playbook, 'w') as f:
            f.write(json.dumps(play))

        path = os.path.join(private_data_dir, 'inventory')
        os.makedirs(path)

        inventory = os.path.join(path, 'hosts')
        with open(inventory, 'w') as f:
            f.write('[all]\nlocalhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"')

        cmdline('run', private_data_dir, '-p', playbook, '--inventory', inventory)

        assert main() == 0

        with open(playbook) as f:
            assert json.loads(f.read()) == play

    finally:
        shutil.rmtree(private_data_dir)


def test_cmdline_playbook_hosts():
    """Test error is raised with trying to pass '--hosts' with '-p'
    """
    cmdline('run', 'private_data_dir', '-p', 'fake', '--hosts', 'all')
    with pytest.raises(SystemExit) as exc:
        main()
        assert exc == 1


def test_cmdline_includes_one_option():
    """Test error is raised if not '-p', '-m' or '-r'
    """
    cmdline('run', 'private_data_dir')
    with pytest.raises(SystemExit) as exc:
        main()
        assert exc == 1


def test_cmdline_cmdline_override(is_pre_ansible28):
    try:
        private_data_dir = tempfile.mkdtemp()
        play = [{'hosts': 'all', 'tasks': [{'debug': {'msg': random_string()}}]}]

        path = os.path.join(private_data_dir, 'project')
        os.makedirs(path)

        playbook = os.path.join(path, 'main.yaml')
        with open(playbook, 'w') as f:
            f.write(json.dumps(play))
        path = os.path.join(private_data_dir, 'inventory')
        os.makedirs(path)

        inventory = os.path.join(path, 'hosts')
        with open(inventory, 'w') as f:
            f.write('[all]\nlocalhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"')

        # privateip: removed --hosts command line option from test beause it is
        # not a supported combination of cli options
        # cmdline('run', private_data_dir, '-p', playbook, '--hosts', 'all', '--cmdline', '-e foo=bar')
        cmdline('run', private_data_dir, '-p', playbook, '--cmdline', '-e foo=bar')
        assert main() == 0
    finally:
        shutil.rmtree(private_data_dir)
