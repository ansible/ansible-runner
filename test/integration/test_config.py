from ansible_runner.config._base import BaseConfig


def test_combine_python_and_file_settings(project_fixtures):
    rc = BaseConfig(private_data_dir=str(project_fixtures / 'job_env'), settings={'job_timeout': 40})
    rc._prepare_env()
    assert rc.settings == {'job_timeout': 40, 'process_isolation': True}
