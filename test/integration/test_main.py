# -*- coding: utf-8 -*-
from __future__ import print_function
from ansible_runner.__main__ import main

import os
import codecs
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


def test_help():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2, 'Should raise SystemExit with return code 2'


def test_module_run():
    try:
        rc = main(['-m', 'ping',
                   '--hosts', 'localhost',
                   'run',
                   'ping'])
        assert os.path.exists('./ping')
        assert os.path.exists('./ping/artifacts')
        assert rc == 0
    finally:
        shutil.rmtree('./ping')


def test_module_run_debug():
    try:
        rc = main(['-m', 'ping',
                   '--hosts', 'localhost',
                   '--debug',
                   'run',
                   'ping'])
        assert os.path.exists('./ping')
        assert os.path.exists('./ping/artifacts')
        assert rc == 0
    finally:
        shutil.rmtree('./ping')


@pytest.mark.serial
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
    ensure_removed("test/integration/artifacts")


def test_role_run_abs():
    with temp_directory() as temp_dir:
        rc = main(['-r', 'benthomasson.hello_role',
                   '--hosts', 'localhost',
                   '--roles-path', os.path.join(HERE, 'project/roles'),
                   'run',
                   temp_dir])
    assert rc == 0


def test_role_logfile():
    try:
        rc = main(['-r', 'benthomasson.hello_role',
                   '--hosts', 'localhost',
                   '--roles-path', 'test/integration/project/roles',
                   '--logfile', 'new_logfile',
                   'run',
                   'test/integration'])
        assert os.path.exists('new_logfile')
        assert rc == 0
    finally:
        ensure_removed("test/integration/artifacts")


def test_role_logfile_abs():
    try:
        with temp_directory() as temp_dir:
            rc = main(['-r', 'benthomasson.hello_role',
                       '--hosts', 'localhost',
                       '--roles-path', os.path.join(HERE, 'project/roles'),
                       '--logfile', 'new_logfile',
                       'run',
                       temp_dir])
        assert os.path.exists('new_logfile')
        assert rc == 0
    finally:
        ensure_removed("new_logfile")


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
        ensure_removed("new_logfile")


@pytest.mark.serial
def test_role_run_clean():

    rc = main(['-r', 'benthomasson.hello_role',
               '--hosts', 'localhost',
               '--roles-path', 'test/integration/roles',
               'run',
               "test/integration"])
    assert rc == 0
    ensure_removed("test/integration/artifacts")


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
    ensure_removed("test/integration/artifacts")


def test_role_run_artifacts_dir_abs():
    try:
        with temp_directory() as temp_dir:
            rc = main(['-r', 'benthomasson.hello_role',
                       '--hosts', 'localhost',
                       '--roles-path', os.path.join(HERE, 'project/roles'),
                       '--artifact-dir', 'otherartifacts',
                       'run',
                       temp_dir])
        assert os.path.exists(os.path.join('.', 'otherartifacts'))
        assert rc == 0
    finally:
        shutil.rmtree(os.path.join('.', 'otherartifacts'))


@pytest.mark.parametrize('envvars', [
    {'msg': 'hi'},
    {
        'msg': u'utf-8-䉪ቒ칸ⱷ?噂폄蔆㪗輥',
        u'蔆㪗輥': u'䉪ቒ칸'
    }],
    ids=['regular-text', 'utf-8-text']
)
def test_role_run_env_vars(envvars):

    with temp_directory() as temp_dir:
        ensure_directory(os.path.join(temp_dir, 'env'))
        with codecs.open(os.path.join(temp_dir, 'env/envvars'), 'w', encoding='utf-8') as f:
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
        shutil.copy(os.path.join(HERE, 'inventory/localhost'), os.path.join(temp_dir, 'inventory/localhost'))

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
        shutil.copy(os.path.join(HERE, 'inventory/localhost'), os.path.join(temp_dir, 'inventory/localhost'))

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


@pytest.mark.serial
def test_playbook_start():

    with temp_directory() as temp_dir:
        project_dir = os.path.join(temp_dir, 'project')
        ensure_directory(project_dir)
        shutil.copy(os.path.join(HERE, 'project/hello.yml'), project_dir)
        ensure_directory(os.path.join(temp_dir, 'inventory'))
        shutil.copy(os.path.join(HERE, 'inventory/localhost'), os.path.join(temp_dir, 'inventory/localhost'))

        # privateip: removed --hosts command line option from test beause it is
        # not a supported combination of cli options
        p = multiprocessing.Process(target=main,
                                    args=[['-p', 'hello.yml',
                                           '--inventory', os.path.join(HERE, 'inventory/localhost'),
                                           #'--hosts', 'localhost',
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
