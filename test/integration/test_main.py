from __future__ import print_function
from ansible_runner.__main__ import main

import os
import multiprocessing
import shutil
import yaml
import tempfile
import time
from contextlib import contextmanager
import pytest


from ansible_runner.exceptions import AnsibleRunnerException

HERE = os.path.abspath(os.path.dirname(__file__))


def ensure_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


def ensure_removed(file_path):

    if os.path.exists(file_path):
        os.unlink(file_path)


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


def test_help():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2, 'Should raise SystemExit with return code 2'


def test_module_run():

    rc = main(['-m', 'ping',
               '--hosts', 'localhost',
               'run',
               'ping'])
    assert rc == 0


def test_module_run_debug():

    rc = main(['-m', 'ping',
               '--hosts', 'localhost',
               '--debug',
               'run',
               'ping'])
    assert rc == 0


def test_module_run_clean():

    with temp_directory() as temp_dir:
        rc = main(['-m', 'ping',
                   '--hosts', 'localhost',
                   'run',
                   temp_dir])
    assert rc == 0


def test_role_run():

    rc = main(['-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', 'test/integration/roles',
               'run',
               "test/integration"])
    assert rc == 0


def test_role_run_abs():
    with temp_directory() as temp_dir:
        rc = main(['-r', 'benthomasson.hello_role',
                   '--hosts', 'localhost',
                   '--roles-path', os.path.join(HERE, 'project/roles'),
                   'run',
                   temp_dir])
    assert rc == 0


def test_role_logfile():

    rc = main(['-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', 'test/integration/project/roles',
               '--logfile', 'new_logfile',
               'run',
               'test/integration'])
    assert rc == 0


def test_role_logfile_abs():
    with temp_directory() as temp_dir:
        rc = main(['-r', 'benthomasson.hello_role',
                   '--hosts', 'localhost',
                   '--roles-path', os.path.join(HERE, 'project/roles'),
                   '--logfile', 'new_logfile',
                   'run',
                   temp_dir])
    assert rc == 0


def test_role_bad_project_dir():

    with open("bad_project_dir", 'w') as f:
        f.write('not a directory')

    try:
        with pytest.raises(OSError):
            main(['-r', 'benthomasson.hello_role',
                  '--hosts', 'localhost',
                  '--roles-path', os.path.join(HERE, 'project/roles'),
                  '--logfile', 'new_logfile',
                  'run',
                  'bad_project_dir'])
    finally:
        os.unlink('bad_project_dir')


def test_role_run_clean():

    rc = main(['-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', 'test/integration/roles',
               'run',
               "test/integration"])
    assert rc == 0


def test_role_run_cmd_line_abs():
    with temp_directory() as temp_dir:
        rc = main(['-r', 'benthomasson.hello_role',
                   '--hosts', 'localhost',
                   '--roles-path', os.path.join(HERE, 'project/roles'),
                   'run',
                   temp_dir])
    assert rc == 0


def test_role_run_artifacts_dir():

    rc = main(['-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', 'test/integration/roles',
               '--artifact-dir', 'otherartifacts',
               'run',
               "test/integration"])
    assert rc == 0


def test_role_run_artifacts_dir_abs():
    with temp_directory() as temp_dir:
        rc = main(['-r', 'benthomasson.hello_role',
                   '--hosts', 'localhost',
                   '--roles-path', os.path.join(HERE, 'project/roles'),
                   '--artifact-dir', 'otherartifacts',
                   'run',
                   temp_dir])
    assert rc == 0


@pytest.mark.parametrize('envvars', [
    {'msg': 'hi'},
    {'msg': b'\xf0\x98\x90\x9d\xe5\x83\xac\xe2\xb2\x82\xeb\x8d\xb6'.decode('utf-8')}
])
def test_role_run_env_vars(envvars):

    with temp_directory() as temp_dir:
        ensure_directory(os.path.join(temp_dir, 'env'))
        with open(os.path.join(temp_dir, 'env/envvars'), 'w') as f:
            f.write(yaml.dump(envvars))

        rc = main(['-r', 'benthomasson.hello_role',
                   '--hosts', 'localhost',
                   '--roles-path', os.path.join(HERE, 'project/roles'),
                   'run',
                   temp_dir])
    assert rc == 0


def test_role_run_args():

    with temp_directory() as temp_dir:
        rc = main(['-r', 'benthomasson.hello_role',
                   '--hosts', 'localhost',
                   '--roles-path', os.path.join(HERE, 'project/roles'),
                   '--role-vars', 'msg=hi',
                   'run',
                   temp_dir])
    assert rc == 0


def test_role_run_inventory():

    with temp_directory() as temp_dir:
        ensure_directory(os.path.join(temp_dir, 'inventory'))
        shutil.copy(os.path.join(HERE, 'inventories/localhost'), os.path.join(temp_dir, 'inventory/localhost'))

        rc = main(['-r', 'benthomasson.hello_role',
                   '--hosts', 'localhost',
                   '--roles-path', os.path.join(HERE, 'project/roles'),
                   '--inventory', 'localhost',
                   'run',
                   temp_dir])
    assert rc == 0


def test_role_run_inventory_missing():

    with temp_directory() as temp_dir:
        ensure_directory(os.path.join(temp_dir, 'inventory'))
        shutil.copy(os.path.join(HERE, 'inventories/localhost'), os.path.join(temp_dir, 'inventory/localhost'))

        with pytest.raises(AnsibleRunnerException):
            main(['-r', 'benthomasson.hello_role',
                  '--hosts', 'localhost',
                  '--roles-path', os.path.join(HERE, 'project/roles'),
                  '--inventory', 'does_not_exist',
                  'run',
                  temp_dir])


def test_role_start():


    with temp_directory() as temp_dir:
        p = multiprocessing.Process(target=main,
                                    args=[['-r', 'benthomasson.hello_role',
                                           '--hosts', 'localhost',
                                           '--roles-path', os.path.join(HERE, 'project/roles'),
                                           'start',
                                           temp_dir]])
        p.start()
        p.join()


def test_playbook_start():

    with temp_directory() as temp_dir:
        project_dir = os.path.join(temp_dir, 'project')
        ensure_directory(project_dir)
        shutil.copy(os.path.join(HERE, 'project/hello.yml'), project_dir)
        ensure_directory(os.path.join(temp_dir, 'inventory'))
        shutil.copy(os.path.join(HERE, 'inventories/localhost'), os.path.join(temp_dir, 'inventory/localhost'))


        p = multiprocessing.Process(target=main,
                                    args=[['-p', 'hello.yml',
                                           '--inventory', os.path.join(HERE, 'inventories/localhost'),
                                           '--hosts', 'localhost',
                                           'start',
                                           temp_dir]])
        p.start()


        time.sleep(5)

        assert os.path.exists(os.path.join(temp_dir, 'pid'))

        rc = main(['is-alive', temp_dir])
        assert rc == 0
        rc = main(['stop', temp_dir])
        assert rc == 0

        time.sleep(1)

        rc = main(['is-alive', temp_dir])
        assert rc == 1

        ensure_removed(os.path.join(temp_dir, 'pid'))

        rc = main(['stop', temp_dir])
    assert rc == 1

