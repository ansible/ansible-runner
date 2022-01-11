from ansible_runner.config._base import BaseConfig
from ansible_runner.interface import run

import os


def test_combine_python_and_file_settings(project_fixtures):
    rc = BaseConfig(private_data_dir=str(project_fixtures / 'job_env'), settings={'job_timeout': 40})
    rc._prepare_env()
    assert rc.settings == {'job_timeout': 40, 'process_isolation': True}


def test_default_ansible_callback(project_fixtures):
    """This is the reference case for stdout customization tests, assures default stdout callback is used"""
    res = run(private_data_dir=str(project_fixtures / 'debug'), playbook='debug.yml')
    stdout = res.stdout.read()
    assert res.rc == 0, stdout

    assert 'ok: [host_1] => {' in stdout, stdout
    assert '"msg": "Hello world!"' in stdout, stdout


def test_custom_stdout_callback_via_host_environ(project_fixtures, mocker):
    mocker.patch.dict(os.environ, {'ANSIBLE_STDOUT_CALLBACK': 'minimal'})
    res = run(private_data_dir=str(project_fixtures / 'debug'), playbook='debug.yml')
    stdout = res.stdout.read()
    assert res.rc == 0, stdout

    assert 'host_1 | SUCCESS => {' in stdout, stdout
    assert '"msg": "Hello world!"' in stdout, stdout


def test_custom_stdout_callback_via_envvars(project_fixtures, mocker):
    res = run(private_data_dir=str(project_fixtures / 'debug'), playbook='debug.yml', envvars={'ANSIBLE_STDOUT_CALLBACK': 'minimal'})
    stdout = res.stdout.read()
    assert res.rc == 0, stdout

    assert 'host_1 | SUCCESS => {' in stdout, stdout
    assert '"msg": "Hello world!"' in stdout, stdout
