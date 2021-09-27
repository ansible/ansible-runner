import random
import os
import time

from ansible_runner.cleanup import cleanup_dirs
from ansible_runner.config.runner import RunnerConfig


def test_simple_dir_cleanup_with_exclusions(tmp_path):
    paths = []
    for i in range(0, 6, 2):
        trailing = ''.join(random.choice("abcdefica3829") for i in range(8))
        path = tmp_path / f'pattern_{i}_{trailing}'
        path.mkdir()
        paths.append(str(path))

    a_file_path = os.path.join(tmp_path, 'pattern_32_donotcleanme')
    with open(a_file_path, 'w') as f:
        f.write('this is a file and should not be cleaned by the cleanup command')

    keep_dir_path = tmp_path / 'pattern_42_alsokeepme'
    keep_dir_path.mkdir()

    ct = cleanup_dirs(pattern=str(tmp_path / 'pattern_*_*'), exclude_strings=[42], grace_period=0)
    assert ct == 3  # cleaned up 3 private_data_dirs

    for path in paths:
        assert not os.path.exists(path)

    assert os.path.exists(a_file_path)
    assert os.path.exists(str(keep_dir_path))

    assert cleanup_dirs(pattern=str(tmp_path / 'pattern_*_*'), exclude_strings=[42], grace_period=0) == 0  # no more to cleanup


def test_cleanup_command_grace_period(tmp_path):
    old_dir = str(tmp_path / 'modtime_old_xyz')
    new_dir = str(tmp_path / 'modtime_new_abc')
    os.mkdir(old_dir)
    time.sleep(1)
    os.mkdir(new_dir)
    ct = cleanup_dirs(pattern=str(tmp_path / 'modtime_*_*'), grace_period=1. / 60.)
    assert ct == 1
    assert not os.path.exists(old_dir)
    assert os.path.exists(new_dir)


def test_registry_auth_cleanup(tmp_path):
    pdd_path = tmp_path / 'private_data_dir'
    pdd_path.mkdir()
    private_data_dir = str(pdd_path)

    rc = RunnerConfig(
        private_data_dir=private_data_dir,
        playbook='ping.yml',
        process_isolation_executable='podman',
        process_isolation=True,
        container_image='foo.invalid/alan/runner',
        container_auth_data={'host': 'https://somedomain.invalid', 'username': 'foouser', 'password': '349sk34'},
        ident='awx_123'
    )
    rc.prepare()
    assert rc.registry_auth_path
    assert os.path.exists(rc.registry_auth_path)

    ct = cleanup_dirs(pattern=private_data_dir, grace_period=0)
    assert ct == 1

    assert not os.path.exists(private_data_dir)
    assert not os.path.exists(rc.registry_auth_path)
