import os
import sys
import uuid
import json
import random
import string
import tempfile
import shutil

from pytest import raises

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

    cmdline('run', tmpfile)

    try:
        with raises(OSError):
            main()
    finally:
        os.remove(tmpfile)


def test_cmdline_playbook():
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
            f.write('localhost')

        cmdline('run', private_data_dir, '-p', playbook, '--inventory', inventory)

        with raises(SystemExit) as exc:
            main()
            assert exc.type == SystemExit
            assert exc.value.code == 0

        with open(playbook) as f:
            assert json.loads(f.read()) == play

        with open(inventory) as f:
            assert f.read() == 'localhost'

    finally:
        shutil.rmtree(private_data_dir)


def test_cmdline_playbook_hosts():
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
            f.write('localhost')

        cmdline('run', private_data_dir, '-p', playbook, '--hosts', 'all')

        with raises(SystemExit) as exc:
            main()
            assert exc.type == SystemExit
            assert exc.value.code == 0

        with open(playbook) as f:
            assert json.loads(f.read()) == play

        with open(inventory) as f:
            assert f.read() == 'all'

    finally:
        shutil.rmtree(private_data_dir)


