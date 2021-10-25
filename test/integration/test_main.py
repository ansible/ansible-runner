# -*- coding: utf-8 -*-
import multiprocessing

from ansible_runner.__main__ import main

import pytest
import yaml


from ansible_runner.exceptions import AnsibleRunnerException
from test.utils.common import iterate_timeout


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


def test_role_run(project_fixtures):
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', str(project_fixtures / 'use_role' / 'roles'),
               str(project_fixtures / 'use_role')])

    artifact_dir = project_fixtures / 'use_role' / 'artifacts'
    assert artifact_dir.exists()
    assert rc == 0


def test_role_logfile(project_fixtures):
    logfile = project_fixtures / 'use_role' / 'test_role_logfile'
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', str(project_fixtures / 'use_role' / 'roles'),
               '--logfile', str(logfile),
               str(project_fixtures / 'use_role')])

    assert logfile.exists()
    assert rc == 0


def test_role_bad_project_dir(tmp_path, project_fixtures):
    bad_project_path = tmp_path / "bad_project_dir"
    bad_project_path.write_text('not a directory')

    with pytest.raises(OSError):
        main(['run', '-r', 'benthomasson.hello_role',
              '--hosts', 'localhost',
              '--roles-path', str(project_fixtures / 'use_role' / 'roles'),
              '--logfile', str(project_fixtures / 'use_role' / 'new_logfile'),
              str(bad_project_path)])


@pytest.mark.parametrize('envvars', [
    {'msg': 'hi'},
    {
        'msg': u'utf-8-䉪ቒ칸ⱷ?噂폄蔆㪗輥',
        u'蔆㪗輥': u'䉪ቒ칸'
    }],
    ids=['regular-text', 'utf-8-text']
)
def test_role_run_env_vars(envvars, project_fixtures):
    env_path = project_fixtures / 'use_role' / 'env'

    env_vars = env_path / 'envvars'
    with env_vars.open('a', encoding='utf-8') as f:
        f.write(yaml.dump(envvars))

    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', str(project_fixtures / 'use_role' / 'roles'),
               str(project_fixtures / 'use_role')])

    assert rc == 0


def test_role_run_args(project_fixtures):
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', str(project_fixtures / 'use_role' / 'roles'),
               '--role-vars', 'msg=hi',
               str(project_fixtures / 'use_role')])

    assert rc == 0


def test_role_run_inventory(project_fixtures):
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'testhost',
               '--roles-path', str(project_fixtures / 'use_role' / 'roles'),
               '--inventory', str(project_fixtures / 'use_role' / 'inventory'),
               str(project_fixtures / 'use_role')])

    assert rc == 0


def test_role_run_inventory_missing(project_fixtures):
    with pytest.raises(AnsibleRunnerException):
        main(['run', '-r', 'benthomasson.hello_role',
              '--hosts', 'testhost',
              '--roles-path', str(project_fixtures / 'use_role' / 'roles'),
              '--inventory', 'does_not_exist',
              str(project_fixtures / 'use_role')])


def test_role_start(project_fixtures):
    mpcontext = multiprocessing.get_context('fork')
    p = mpcontext.Process(
        target=main,
        args=[[
            'start',
            '-r', 'benthomasson.hello_role',
            '--hosts', 'localhost',
            '--roles-path', str(project_fixtures / 'use_role' / 'roles'),
            str(project_fixtures / 'use_role'),
        ]]
    )
    p.start()
    p.join()


def test_playbook_start(project_fixtures):
    private_data_dir = project_fixtures / 'sleep'

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
