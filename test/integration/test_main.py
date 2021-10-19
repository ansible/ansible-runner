# -*- coding: utf-8 -*-
import os
import multiprocessing
import shutil
import tempfile

from contextlib import contextmanager

from ansible_runner.__main__ import main

import pytest
import yaml


from ansible_runner.exceptions import AnsibleRunnerException
from test.utils.common import iterate_timeout


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
    private_data_dir = tmp_path / 'ping'
    rc = main(['run', '-m', 'ping',
               '--hosts', 'localhost',
               str(private_data_dir)])

    assert private_data_dir.exists()
    assert private_data_dir.joinpath('artifacts').exists()
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


def test_role_run(test_data_dir):
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', str(test_data_dir / 'use_role' / 'roles'),
               str(test_data_dir / 'use_role')])

    artifact_dir = test_data_dir / 'use_role' / 'artifacts'
    assert artifact_dir.exists()
    assert rc == 0


def test_role_logfile(test_data_dir):
    logfile = test_data_dir / 'use_role' / 'test_role_logfile'
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', str(test_data_dir / 'use_role' / 'roles'),
               '--logfile', str(logfile),
               str(test_data_dir / 'use_role')])

    assert logfile.exists()
    assert rc == 0


def test_role_bad_project_dir(tmp_path, test_data_dir):
    bad_project_path = tmp_path / "bad_project_dir"
    bad_project_path.write_text('not a directory')

    with pytest.raises(OSError):
        main(['run', '-r', 'benthomasson.hello_role',
              '--hosts', 'localhost',
              '--roles-path', str(test_data_dir / 'use_role' / 'roles'),
              '--logfile', str(test_data_dir / 'use_role' / 'new_logfile'),
              str(bad_project_path)])


@pytest.mark.parametrize('envvars', [
    {'msg': 'hi'},
    {
        'msg': u'utf-8-䉪ቒ칸ⱷ?噂폄蔆㪗輥',
        u'蔆㪗輥': u'䉪ቒ칸'
    }],
    ids=['regular-text', 'utf-8-text']
)
def test_role_run_env_vars(envvars, test_data_dir):
    env_path = test_data_dir / 'use_role' / 'env'

    env_vars = env_path / 'envvars'
    with env_vars.open('a', encoding='utf-8') as f:
        f.write(yaml.dump(envvars))

    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', str(test_data_dir / 'use_role' / 'roles'),
               str(test_data_dir / 'use_role')])

    assert rc == 0


def test_role_run_args(test_data_dir):
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', str(test_data_dir / 'use_role' / 'roles'),
               '--role-vars', 'msg=hi',
               str(test_data_dir / 'use_role')])

    assert rc == 0


def test_role_run_inventory(test_data_dir):
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'testhost',
               '--roles-path', str(test_data_dir / 'use_role' / 'roles'),
               '--inventory', str(test_data_dir / 'use_role' / 'inventory'),
               str(test_data_dir / 'use_role')])

    assert rc == 0


def test_role_run_inventory_missing(test_data_dir):
    with pytest.raises(AnsibleRunnerException):
        main(['run', '-r', 'benthomasson.hello_role',
              '--hosts', 'testhost',
              '--roles-path', str(test_data_dir / 'use_role' / 'roles'),
              '--inventory', 'does_not_exist',
              str(test_data_dir / 'use_role')])


def test_role_start(test_data_dir):
    mpcontext = multiprocessing.get_context('fork')
    p = mpcontext.Process(
        target=main,
        args=[[
            'start',
            '-r', 'benthomasson.hello_role',
            '--hosts', 'localhost',
            '--roles-path', str(test_data_dir / 'use_role' / 'roles'),
            str(test_data_dir / 'use_role'),
        ]]
    )
    p.start()
    p.join()


def test_playbook_start(test_data_dir):
    private_data_dir = test_data_dir / 'sleep'

    mpcontext = multiprocessing.get_context('fork')
    p = mpcontext.Process(
        target=main,
        args=[[
            'start',
            '-p', 'sleep.yml',
            str(private_data_dir),
        ]]
    )
    p.start()

    pid_path = private_data_dir / 'pid'
    for _ in iterate_timeout(30, "pid file creation"):
        if pid_path.exists():
            break

    rc = main(['is-alive', str(private_data_dir)])
    assert rc == 0

    rc = main(['stop', str(private_data_dir)])
    assert rc == 0

    for _ in iterate_timeout(30, "background process to stop"):
        rc = main(['is-alive', str(private_data_dir)])
        if rc == 1:
            break

    rc = main(['stop', str(private_data_dir)])
    assert rc == 1
