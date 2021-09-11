# -*- coding: utf-8 -*-
from __future__ import print_function
from ansible_runner.__main__ import main

import os
import codecs
import multiprocessing
import shutil
import yaml
import time
import pytest


from ansible_runner.exceptions import AnsibleRunnerException

HERE = os.path.abspath(os.path.dirname(__file__))


def iterate_timeout(max_seconds, purpose, interval=2):
    start = time.time()
    count = 0
    while (time.time() < start + max_seconds):
        count += 1
        yield count
        time.sleep(interval)
    raise Exception("Timeout waiting for %s" % purpose)


def test_temp_directory(tmp_path):
    context = dict()

    def will_fail():
        context['saved_temp_dir'] = str(tmp_path)
        assert False

    def will_pass():
        context['saved_temp_dir'] = str(tmp_path)
        assert True

    with pytest.raises(AssertionError):
        will_fail()

    assert os.path.exists(context['saved_temp_dir'])
    shutil.rmtree(context['saved_temp_dir'])

    will_pass()
    assert not os.path.exists(context['saved_temp_dir'])


def test_help():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2, 'Should raise SystemExit with return code 2'


def test_module_run():
    try:
        rc = main(['run', '-m', 'ping',
                   '--hosts', 'localhost',
                   'ping'])
        assert os.path.exists('./ping')
        assert os.path.exists('./ping/artifacts')
        assert rc == 0
    finally:
        if os.path.exists('./ping'):
            shutil.rmtree('./ping')


def test_module_run_debug():
    try:
        rc = main(['run', '-m', 'ping',
                   '--hosts', 'localhost',
                   '--debug',
                   'ping'])
        assert os.path.exists('./ping')
        assert os.path.exists('./ping/artifacts')
        assert rc == 0
    finally:
        if os.path.exists('./ping'):
            shutil.rmtree('./ping')


def test_module_run_clean(tmp_path):
    rc = main(['run', '-m', 'ping',
               '--hosts', 'localhost',
               str(tmp_path)])
    assert rc == 0


def test_role_run(skipif_pre_ansible28, clear_integration_artifacts):
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', 'test/integration/roles',
               "test/integration"])
    assert rc == 0


def test_role_run_abs(tmp_path):
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', os.path.join(HERE, 'project/roles'),
               str(tmp_path)])
    assert rc == 0


def test_role_logfile(skipif_pre_ansible28, clear_integration_artifacts, tmp_path):
    log_file = tmp_path / 'test_role_logfile'
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', 'test/integration/project/roles',
               '--logfile', str(log_file),
               'test/integration'])
    assert log_file.exists()
    assert rc == 0


def test_role_logfile_abs(tmp_path):
    log_file = tmp_path / 'new_logfile'
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', os.path.join(HERE, 'project/roles'),
               '--logfile', str(log_file),
               str(tmp_path)])
    assert log_file.exists()
    assert rc == 0


def test_role_bad_project_dir(tmp_path):
    with open(tmp_path / "bad_project_dir", 'w') as f:
        f.write('not a directory')

    with pytest.raises(OSError):
        main(['run', '-r', 'benthomasson.hello_role',
              '--hosts', 'localhost',
              '--roles-path', os.path.join(HERE, 'project/roles'),
              '--logfile', tmp_path.joinpath('new_logfile').as_posix(),
              tmp_path.joinpath('bad_project_dir').as_posix()])


def test_role_run_clean(skipif_pre_ansible28, clear_integration_artifacts):

    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', 'test/integration/roles',
               "test/integration"])
    assert rc == 0


def test_role_run_cmd_line_abs(tmp_path):
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', os.path.join(HERE, 'project/roles'),
               str(tmp_path)])
    assert rc == 0


def test_role_run_artifacts_dir(skipif_pre_ansible28, clear_integration_artifacts, tmp_path):
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', 'test/integration/roles',
               '--artifact-dir', tmp_path.joinpath('otherartifacts').as_posix(),
               "test/integration"])
    assert rc == 0


def test_role_run_artifacts_dir_abs(skipif_pre_ansible28, tmp_path):
    artifacts_dir = tmp_path / 'otherartifacts'
    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', os.path.join(HERE, 'project/roles'),
               '--artifact-dir', artifacts_dir.as_posix(),
               str(tmp_path)])

    assert artifacts_dir.exists()
    assert rc == 0


@pytest.mark.parametrize('envvars', [
    {'msg': 'hi'},
    {
        'msg': u'utf-8-䉪ቒ칸ⱷ?噂폄蔆㪗輥',
        u'蔆㪗輥': u'䉪ቒ칸'
    }],
    ids=['regular-text', 'utf-8-text']
)
def test_role_run_env_vars(envvars, tmp_path):
    env_path = tmp_path / 'env'
    env_path.mkdir()

    with codecs.open(env_path / 'envvars', 'w', encoding='utf-8') as f:
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
    src_inv = 'inventory/localhost_preansible28' if is_pre_ansible28 else 'inventory/localhost'

    inventory_dir = tmp_path / 'inventory'
    inventory_dir.mkdir()

    inventory = inventory_dir / 'localhost'

    shutil.copy(os.path.join(HERE, src_inv), inventory)

    rc = main(['run', '-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', os.path.join(HERE, 'project/roles'),
               '--inventory', str(inventory),
               str(tmp_path)])

    assert rc == 0


def test_role_run_inventory_missing(is_pre_ansible28, tmp_path):
    src_inv = 'inventory/localhost_preansible28' if is_pre_ansible28 else 'inventory/localhost'
    inventory_dir = tmp_path / 'inventory'
    inventory_dir.mkdir()

    inventory = inventory_dir / 'localhost'

    shutil.copy(os.path.join(HERE, src_inv), inventory)

    with pytest.raises(AnsibleRunnerException):
        main(['run', '-r', 'benthomasson.hello_role',
              '--hosts', 'localhost',
              '--roles-path', os.path.join(HERE, 'project/roles'),
              '--inventory', 'does_not_exist',
              str(tmp_path)])


def test_role_start(tmp_path):
    p = multiprocessing.Process(target=main,
                                args=[['start', '-r', 'benthomasson.hello_role',
                                       '--hosts', 'localhost',
                                       '--roles-path', os.path.join(HERE, 'project/roles'),
                                       str(tmp_path)]])
    p.start()
    p.join()


def test_playbook_start(skipif_pre_ansible28, tmp_path):
    project_dir = tmp_path / 'project'
    project_dir.mkdir()

    shutil.copy(os.path.join(HERE, 'project/hello.yml'), project_dir)

    inventory_dir = tmp_path / 'inventory'
    inventory_dir.mkdir()
    inventory = inventory_dir / 'localhost'

    shutil.copy(os.path.join(HERE, 'inventory/localhost'), inventory)

    # privateip: removed --hosts command line option from test beause it is
    # not a supported combination of cli options
    p = multiprocessing.Process(target=main,
                                args=[['start', '-p', 'hello.yml',
                                       '--inventory', os.path.join(HERE, 'inventory/localhost'),
                                       # '--hosts', 'localhost',
                                       str(tmp_path)]])
    p.start()

    pid_path = tmp_path / 'pid'
    for _ in iterate_timeout(30, "pid file creation"):
        if pid_path.exists():
            break

    rc = main(['is-alive', str(tmp_path)])
    assert rc == 0
    rc = main(['stop', str(tmp_path)])
    assert rc == 0

    for _ in iterate_timeout(30, "background process to stop"):
        rc = main(['is-alive', str(tmp_path)])
        if rc == 1:
            break

    rc = main(['stop', str(tmp_path)])
    assert rc == 1
