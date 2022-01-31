import os
import sys
import uuid
import json
import random
import string

import pytest

import ansible_runner.__main__


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
            ansible_runner.__main__.main()
    finally:
        os.remove(tmpfile)


def save_playbook(**kwargs):
    os.link(kwargs['playbook'], os.path.join(kwargs['private_data_dir'], 'play.yml'))

    raise AttributeError("Raised intentionally")


@pytest.mark.parametrize(
    ('options', 'expected_playbook'),
    (
        (
            ['-r', 'test'],
            [{'hosts': 'all', 'gather_facts': True, 'roles': [{'name': 'test'}]}],
        ),
        (
            ['-r', 'test', '--role-skip-facts'],
            [{'hosts': 'all', 'gather_facts': False, 'roles': [{'name': 'test'}]}],
        ),
        (
            ['-r', 'test', '--role-vars', 'foo=bar'],
            [{'hosts': 'all', 'gather_facts': True, 'roles': [{'name': 'test', 'vars': {'foo': 'bar'}}]}],
        ),
        (
            ['-r', 'test', '--roles-path', '/tmp/roles'],
            [{'hosts': 'all', 'gather_facts': True, 'roles': [{'name': 'test'}]}],
        ),
    )
)
def test_cmdline_role(options, expected_playbook, tmp_path, mocker):
    mocker.patch.object(ansible_runner.__main__, 'run', save_playbook)
    spy = mocker.spy(ansible_runner.__main__, 'run')

    command = ['run', str(tmp_path)]
    command.extend(options)

    rc = ansible_runner.__main__.main(command)

    with open(tmp_path / 'play.yml') as f:
        playbook = json.loads(f.read())

    assert rc == 1
    assert playbook == expected_playbook
    assert spy.call_args.kwargs.get('private_data_dir') == str(tmp_path)


def test_cmdline_role_with_playbook_option():
    """Test error is raised with invalid command line option '-p'
    """
    cmdline('run', 'private_data_dir', '-r', 'fake', '-p', 'fake')
    with pytest.raises(SystemExit) as exc:
        ansible_runner.__main__.main()
        assert exc == 1


def test_cmdline_playbook(tmp_path):
    private_data_dir = tmp_path
    play = [{'hosts': 'all', 'tasks': [{'debug': {'msg': random_string()}}]}]

    path = private_data_dir / 'project'
    path.mkdir()

    playbook = path / 'main.yaml'
    with open(playbook, 'w') as f:
        f.write(json.dumps(play))

    path = private_data_dir / 'inventory'
    os.makedirs(path)

    inventory = path / 'hosts'
    with open(inventory, 'w') as f:
        f.write('[all]\nlocalhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"')

    cmdline('run', str(private_data_dir), '-p', str(playbook), '--inventory', str(inventory))

    assert ansible_runner.__main__.main() == 0

    with open(playbook) as f:
        assert json.loads(f.read()) == play


def test_cmdline_playbook_hosts():
    """Test error is raised with trying to pass '--hosts' with '-p'
    """
    cmdline('run', 'private_data_dir', '-p', 'fake', '--hosts', 'all')
    with pytest.raises(SystemExit) as exc:
        ansible_runner.__main__.main()
        assert exc == 1


def test_cmdline_includes_one_option():
    """Test error is raised if not '-p', '-m' or '-r'
    """
    cmdline('run', 'private_data_dir')
    with pytest.raises(SystemExit) as exc:
        ansible_runner.__main__.main()
        assert exc == 1


def test_cmdline_cmdline_override(tmp_path):
    private_data_dir = tmp_path
    play = [{'hosts': 'all', 'tasks': [{'debug': {'msg': random_string()}}]}]

    path = private_data_dir / 'project'
    path.mkdir()

    playbook = path / 'main.yaml'
    with open(playbook, 'w') as f:
        f.write(json.dumps(play))
    path = private_data_dir / 'inventory'
    os.makedirs(path)

    inventory = path / 'hosts'
    with open(inventory, 'w') as f:
        f.write('[all]\nlocalhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"')

    cmdline('run', str(private_data_dir), '-p', str(playbook), '--cmdline', '-e foo=bar')
    assert ansible_runner.__main__.main() == 0
