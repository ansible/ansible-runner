import sys
import pytest

from ansible_runner.interface import run


TEST_BRANCHES = (
    'devel',
    'milestone',
    'stable-2.16',   # current stable
    'stable-2.15',   # stable - 1
)


@pytest.mark.test_all_runtimes
@pytest.mark.parametrize('branch', TEST_BRANCHES)
@pytest.mark.skipif(sys.platform == 'darwin', reason='does not work on macOS')
def test_adhoc(tmp_path, runtime, branch, container_image_devel):  # pylint: disable=W0613
    # pvt_data_dir is mounted on the container, so it must contain the expected directories
    project_dir = tmp_path / 'project'
    project_dir.mkdir()
    r = run(private_data_dir=str(tmp_path),
            host_pattern='localhost',
            module='shell',
            module_args='pwd',
            process_isolation_executable=runtime,
            process_isolation=True,
            container_image=container_image_devel,
            )

    assert r.status == 'successful'
    assert r.rc == 0
    assert 'ok' in r.stats
    assert 'localhost' in r.stats['ok']
    events = [x['event'] for x in r.events if x['event'] != 'verbose']
    assert len(events) == 4


@pytest.mark.test_all_runtimes
@pytest.mark.parametrize('branch', TEST_BRANCHES)
@pytest.mark.skipif(sys.platform == 'darwin', reason='does not work on macOS')
def test_playbook(tmp_path, runtime, branch, container_image_devel):  # pylint: disable=W0613
    PLAYBOOK = """
- hosts: localhost
  gather_facts: False
  tasks:
    - set_fact:
        foo: bar
"""

    # pvt_data_dir is mounted on the container, so it must contain the expected directories
    project_dir = tmp_path / 'project'
    project_dir.mkdir()
    inventory_dir = tmp_path / 'inventory'
    inventory_dir.mkdir()

    hosts_file = inventory_dir / 'hosts'
    hosts_file.write_text('localhost\n')

    playbook = project_dir / 'test.yml'
    playbook.write_text(PLAYBOOK)

    r = run(private_data_dir=str(tmp_path),
            playbook='test.yml',
            process_isolation_executable=runtime,
            process_isolation=True,
            container_image=container_image_devel,
            )

    expected_events = [
        'playbook_on_start',
        'playbook_on_play_start',
        'playbook_on_task_start',
        'runner_on_start',
        'runner_on_ok',
        'playbook_on_stats',
    ]

    assert r.status == 'successful'
    assert r.rc == 0
    assert 'ok' in r.stats
    assert 'localhost' in r.stats['ok']
    events = [x['event'] for x in r.events if x['event'] != 'verbose']
    assert events == expected_events
