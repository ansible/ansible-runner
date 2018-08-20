from __future__ import print_function
from ansible_runner.__main__ import main

import os
import multiprocessing
import shutil
import yaml
import tempfile
import time
from contextlib import contextmanager
from pytest import raises


from ansible_runner.exceptions import AnsibleRunnerException

HERE = os.path.abspath(os.path.dirname(__file__))


def ensure_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


def ensure_removed(file_path):

    if os.path.exists(file_path):
        os.unlink(file_path)


@contextmanager
def temp_directory():

    temp_dir = tempfile.mkdtemp()
    try:
        yield temp_dir
        shutil.rmtree(temp_dir)
    except BaseException:
        print(temp_dir)
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

    with raises(AssertionError):
        will_fail()
    assert os.path.exists(context['saved_temp_dir'])
    shutil.rmtree(context['saved_temp_dir'])

    will_pass()
    assert not os.path.exists(context['saved_temp_dir'])


def test_help():
    with raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2, 'Should raise SystemExit with return code 2'


def test_module_run():

    main(['-m', 'ping',
          '--hosts', 'localhost',
          'run',
          'ping'])


def test_module_run_clean():

    with temp_directory() as temp_dir:
        main(['-m', 'ping',
              '--hosts', 'localhost',
              'run',
              temp_dir])


def test_role_run():

    main(['-r', 'benthomasson.hello_role',
          '--hosts', 'localhost',
          '--roles-path', 'test/integration/roles',
          'run',
          'hello'])


def test_role_logfile():

    main(['-r', 'benthomasson.hello_role',
          '--hosts', 'localhost',
          '--roles-path', 'test/integration/roles',
          '--logfile', 'new_logfile',
          'run',
          'hello'])


def test_role_bad_project_dir():

    with open("bad_project_dir", 'w') as f:
        f.write('not a directory')

    try:
        with raises(OSError):
            main(['-r', 'benthomasson.hello_role',
                  '--hosts', 'localhost',
                  '--roles-path', 'test/integration/roles',
                  '--logfile', 'new_logfile',
                  'run',
                  'bad_project_dir'])
    finally:
        os.unlink('bad_project_dir')


def test_role_run_clean():

    with temp_directory() as temp_dir:
        main(['-r', 'benthomasson.hello_role',
              '--hosts', 'localhost',
              '--roles-path', 'test/integration/roles',
              'run',
              temp_dir])


def test_role_run_cmd_line():

    main(['-r', 'benthomasson.hello_role',
          '--hosts', 'localhost',
          '--roles-path', 'test/integration/roles',
          '--cmdline', 'msg=hi',
          'run',
          'hello'])

    ensure_removed('hello/env/cmdline')


def test_role_run_artifacts_dir():

    main(['-r', 'benthomasson.hello_role',
          '--hosts', 'localhost',
          '--roles-path', 'test/integration/roles',
          '--artifact-dir', 'otherartifacts',
          'run',
          'hello'])


def test_role_run_env_vars():

    ensure_directory('hello/env')
    with open('hello/env/envvars', 'w') as f:
        f.write(yaml.dump(dict(msg='hi')))

    try:

        main(['-r', 'benthomasson.hello_role',
              '--hosts', 'localhost',
              '--roles-path', 'test/integration/roles',
              'run',
              'hello'])

    finally:
        os.unlink('hello/env/envvars')


def test_role_run_args():

    main(['-r', 'benthomasson.hello_role',
          '--hosts', 'localhost',
          '--roles-path', 'test/integration/roles',
          '--role-vars', 'msg=hi',
          'run',
          'hello'])


def test_role_run_inventory():

    ensure_directory('hello/inventory')
    shutil.copy(os.path.join(HERE, 'inventories/localhost'), 'hello/inventory/localhost')

    main(['-r', 'benthomasson.hello_role',
          '--hosts', 'localhost',
          '--roles-path', 'test/integration/roles',
          '--inventory', 'localhost',
          'run',
          'hello'])


def test_role_run_inventory_missing():

    ensure_directory('hello/inventory')
    shutil.copy(os.path.join(HERE, 'inventories/localhost'), 'hello/inventory/localhost')

    with raises(AnsibleRunnerException):
        main(['-r', 'benthomasson.hello_role',
              '--hosts', 'localhost',
              '--roles-path', 'test/integration/roles',
              '--inventory', 'does_not_exist',
              'run',
              'hello'])


def test_role_start():


    with temp_directory() as temp_dir:
        p = multiprocessing.Process(target=main,
                                    args=[['-r', 'benthomasson.hello_role',
                                           '--hosts', 'localhost',
                                           '--roles-path', 'test/integration/roles',
                                           'start',
                                           temp_dir]])
        p.start()
        p.join()


def test_playbook_start():

    with temp_directory() as temp_dir:
        project_dir = os.path.join(temp_dir, 'project')
        ensure_directory(project_dir)
        shutil.copy(os.path.join(HERE, 'playbooks/hello.yml'), project_dir)


        p = multiprocessing.Process(target=main,
                                    args=[['-p', 'hello.yml',
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

