# -*- coding: utf-8 -*-
import logging
import multiprocessing
import subprocess
import sys

from test.utils.common import iterate_timeout

import pytest
import yaml

from ansible_runner.__main__ import main


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
        'msg': 'utf-8-䉪ቒ칸ⱷ?噂폄蔆㪗輥',
        '蔆㪗輥': '䉪ቒ칸'
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
    with pytest.raises(SystemExit) as exc:
        main(['run', '-r', 'benthomasson.hello_role',
              '--hosts', 'testhost',
              '--roles-path', str(project_fixtures / 'use_role' / 'roles'),
              '--inventory', 'does_not_exist',
              str(project_fixtures / 'use_role')])
    assert exc.value.code == 1


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


def start_in_background(args):
    """Run ``main(args)`` in a forked process and return it, already started."""
    mpcontext = multiprocessing.get_context('fork')
    p = mpcontext.Process(target=main, args=[args])
    p.start()
    return p


def test_start_when_already_running(project_fixtures):
    private_data_dir = project_fixtures / 'sleep'
    pid_path = private_data_dir / 'pid'

    args = ['start', '-p', 'sleep.yml', str(private_data_dir)]
    start_in_background(args).join()

    for _ in iterate_timeout(30, "pid file creation"):
        if pid_path.exists():
            break
    running_pid = pid_path.read_text().strip()

    try:
        # A second start against the same private data dir must refuse to launch
        # rather than traceback, and must leave the running daemon's pid file alone.
        second = start_in_background(args)
        second.join()
        assert second.exitcode == 1
        assert pid_path.read_text().strip() == running_pid
    finally:
        assert main(['stop', str(private_data_dir)]) == 0


def test_start_reclaims_stale_pidfile(project_fixtures):
    private_data_dir = project_fixtures / 'sleep'
    pid_path = private_data_dir / 'pid'

    # A pid file left behind by a process that no longer exists (SIGKILL, reboot, ...)
    # must not block subsequent starts.
    proc = subprocess.Popen([sys.executable, '-c', ''])  # pylint: disable=R1732
    proc.wait()
    pid_path.write_text(f"{proc.pid}\n")

    start_in_background(['start', '-p', 'sleep.yml', str(private_data_dir)]).join()

    try:
        for _ in iterate_timeout(30, "stale pid file to be reclaimed"):
            if pid_path.exists() and pid_path.read_text().strip() != str(proc.pid):
                break
        assert main(['is-alive', str(private_data_dir)]) == 0
    finally:
        assert main(['stop', str(private_data_dir)]) == 0


@pytest.fixture
def no_logfile_handler():
    """Undo any logfile handler an earlier test left on the process wide debug logger.

    ``output.set_logfile()`` is a no-op once a handler named ``logfile`` is registered,
    and the forked process inherits that state.
    """
    logger = logging.getLogger('ansible-runner.debug')
    saved = list(logger.handlers)
    logger.handlers = [h for h in saved if h.get_name() != 'logfile']
    yield
    logger.handlers = saved


def test_start_writes_logfile(project_fixtures, tmp_path, no_logfile_handler):  # pylint: disable=W0613,W0621
    # The logfile handler is opened before the process detaches, so it only survives
    # if daemonizing leaves inherited file descriptors alone.
    private_data_dir = project_fixtures / 'use_role'
    logfile = tmp_path / 'runner.log'

    start_in_background([
        'start',
        '--debug',
        '--logfile', str(logfile),
        '-r', 'benthomasson.hello_role',
        '--hosts', 'localhost',
        '--roles-path', str(private_data_dir / 'roles'),
        str(private_data_dir),
    ]).join()

    try:
        # Assert on a line role_manager() logs from inside the ``with`` block, after
        # the process has detached. Merely checking that the file is non-empty would
        # pass on the entries written by the launcher before it forked.
        for _ in iterate_timeout(30, "daemon to write to the logfile after detaching"):
            if logfile.exists() and 'setting ANSIBLE_ROLES_PATH' in logfile.read_text():
                break
    finally:
        # The run is short, so it may well have finished already: the return code of
        # stop is deliberately not asserted. Leaving it running would let the fixture
        # teardown delete the private data dir out from under it.
        main(['stop', str(private_data_dir)])
        for _ in iterate_timeout(30, "background process to stop"):
            if main(['is-alive', str(private_data_dir)]) == 1:
                break
