# -*- coding: utf-8 -*-
from __future__ import print_function
from ansible_runner.__main__ import main

import os
import codecs
import multiprocessing
import shutil
import yaml
import tempfile
from contextlib import contextmanager
import pytest


from ansible_runner.exceptions import AnsibleRunnerException
from test.utils.common import iterate_timeout

HERE = os.path.abspath(os.path.dirname(__file__))


def ensure_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


def ensure_removed(path):
    if os.path.exists(path):
        if os.path.isfile(path):
            os.unlink(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)


@contextmanager
def temp_directory(files=None):
    temp_dir = tempfile.mkdtemp()
    print(temp_dir)
    try:
        yield temp_dir
        shutil.rmtree(temp_dir)
    except BaseException:
        if files is not None:
            for file in files:
                if os.path.exists(file):
                    with open(file) as f:
                        print(f.read())
        raise


def test_temp_directory():

    context = dict()

    def will_fail():
        with temp_directory() as temp_dir:
            context['saved_temp_dir'] = temp_dir
            assert False

    def will_pass():
        with temp_directory() as temp_dir:
            context['saved_temp_dir'] = temp_dir
            assert True

    with pytest.raises(AssertionError):
        will_fail()
    assert os.path.exists(context['saved_temp_dir'])
    shutil.rmtree(context['saved_temp_dir'])

    will_pass()
    assert not os.path.exists(context['saved_temp_dir'])


@pytest.mark.parametrize(
    ('command', 'expected'),
    (
        (None, {'out': 'These are common Ansible Runner commands', 'err': ''}),
        ([], {'out': 'These are common Ansible Runner commands', 'err': ''}),
        (['run'], {'out': '', 'err': 'the following arguments are required'}),
    )
)
def test_help(command, expected, capsys, monkeypatch):
    # Ensure that sys.argv of the test command does not affect the test environment.
    monkeypatch.setattr('sys.argv', command or [])

    with pytest.raises(SystemExit) as exc:
        main(command)

    stdout, stderr = capsys.readouterr()

    assert exc.value.code == 2, 'Should raise SystemExit with return code 2'
    assert expected['out'] in stdout
    assert expected['err'] in stderr


def test_module_run(tmp_path):
    pvt_data_dir = tmp_path / 'ping'
    rc = main(['run', '-m', 'ping',
               '--hosts', 'localhost',
               str(pvt_data_dir)])
    assert pvt_data_dir.exists()
    assert pvt_data_dir.joinpath('artifacts').exists()
    assert rc == 0


def test_module_run_debug(tmp_path):
    output = tmp_path / 'ping'
    rc = main(['run', '-m', 'ping',
               '--hosts', 'localhost',
               '--debug',
               str(output)])

    assert output.exists()
    assert output.joinpath('artifacts').exists()
    assert rc == 0


def test_module_run_clean(tmp_path):
    rc = main(['run', '-m', 'ping',
               '--hosts', 'localhost',
               str(tmp_path)])
    assert rc == 0


def test_role_run(skipif_pre_ansible28, tmp_path):
    artifact_dir = tmp_path / "otherartifacts"
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', 'test/integration/roles',
               # Specify artifact dir when private_data_dir is 'test/integration' to prevent collisions
               '--artifact-dir', str(artifact_dir),
               "test/integration"])
    # Assert that the specified artifacts directory is created
    assert artifact_dir.exists()
    assert rc == 0


def test_role_run_abs(tmp_path):
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', os.path.join(HERE, 'project/roles'),
               str(tmp_path)])
    # Assert that the artifacts directory is created in private_data_dir
    assert tmp_path.joinpath('artifacts').exists()
    assert rc == 0


def test_role_logfile(skipif_pre_ansible28, tmp_path):
    logfile = tmp_path.joinpath('test_role_logfile')
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', 'test/integration/project/roles',
               '--logfile', str(logfile),
               '--artifact-dir', str(tmp_path),
               'test/integration'])
    assert logfile.exists()
    assert rc == 0


def test_role_bad_project_dir():

    with open("bad_project_dir", 'w') as f:
        f.write('not a directory')

    try:
        with pytest.raises(OSError):
            main(['run', '-r', 'benthomasson.hello_role',
                  '--hosts', 'localhost',
                  '--roles-path', os.path.join(HERE, 'project/roles'),
                  '--logfile', 'new_logfile',
                  'bad_project_dir'])
    finally:
        os.unlink('bad_project_dir')
        ensure_removed("new_logfile")


@pytest.mark.parametrize('envvars', [
    {'msg': 'hi'},
    {
        'msg': u'utf-8-䉪ቒ칸ⱷ?噂폄蔆㪗輥',
        u'蔆㪗輥': u'䉪ቒ칸'
    }],
    ids=['regular-text', 'utf-8-text']
)
def test_role_run_env_vars(tmp_path, envvars):

    ensure_directory(str(tmp_path / 'env'))
    with codecs.open(str(tmp_path / 'env/envvars'), 'w', encoding='utf-8') as f:
        f.write(yaml.dump(envvars))

    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', os.path.join(HERE, 'project/roles'),
               str(tmp_path)])
    assert rc == 0


def test_role_run_args(tmp_path):

    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', os.path.join(HERE, 'project/roles'),
               '--role-vars', 'msg=hi',
               str(tmp_path)])
    assert rc == 0


def test_role_run_inventory(is_pre_ansible28, tmp_path):

    inv = 'inventory/localhost_preansible28' if is_pre_ansible28 else 'inventory/localhost'
    ensure_directory(str(tmp_path / 'inventory'))
    inv_file = tmp_path / 'inventory' / 'localhost'
    shutil.copy(os.path.join(HERE, inv), str(inv_file))

    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', os.path.join(HERE, 'project/roles'),
               '--inventory', str(inv_file),
               str(tmp_path)])
    assert rc == 0


def test_role_run_inventory_missing(is_pre_ansible28, tmp_path):
    with pytest.raises(AnsibleRunnerException):
        main(['run', '-r', 'benthomasson.hello_role',
              '--hosts', 'localhost',
              '--roles-path', os.path.join(HERE, 'project/roles'),
              '--inventory', 'does_not_exist',
              str(tmp_path)])


def test_role_start(tmp_path):

    mpcontext = multiprocessing.get_context('fork')
    p = mpcontext.Process(
        target=main,
        args=[[
            'start',
            '-r', 'benthomasson.hello_role',
            '--hosts', 'localhost',
            '--roles-path', os.path.join(HERE, 'project/roles'),
            str(tmp_path),
        ]]
    )
    p.start()
    p.join()


def test_playbook_start(skipif_pre_ansible28, tmp_path):
    temp_dir = str(tmp_path)
    inv = 'inventory/localhost'
    project_dir = str(tmp_path / 'project')
    ensure_directory(project_dir)
    shutil.copy(os.path.join(HERE, 'project/hello.yml'), project_dir)

    inventory_dir = tmp_path / 'inventory'
    ensure_directory(str(inventory_dir))
    inventory_file = str(inventory_dir / 'localhost')
    shutil.copy(os.path.join(HERE, inv), inventory_file)

    mpcontext = multiprocessing.get_context('fork')
    p = mpcontext.Process(
        target=main,
        args=[[
            'start',
            '-p', 'hello.yml',
            '--inventory', inventory_file,
            temp_dir,
        ]]
    )
    p.start()

    pid_path = os.path.join(temp_dir, 'pid')
    for _ in iterate_timeout(30, "pid file creation"):
        if os.path.exists(pid_path):
            break

    rc = main(['is-alive', temp_dir])
    assert rc == 0
    rc = main(['stop', temp_dir])
    assert rc == 0

    for _ in iterate_timeout(30, "background process to stop"):
        rc = main(['is-alive', temp_dir])
        if rc == 1:
            break

    ensure_removed(pid_path)

    rc = main(['stop', temp_dir])
    assert rc == 1
