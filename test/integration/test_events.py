import pytest
import tempfile
from distutils.version import LooseVersion
import pkg_resources
import json
import os

from ansible_runner import run, run_async


def test_basic_events(is_run_async=False,g_facts=False):
    tdir = tempfile.mkdtemp()
    inventory = "localhost ansible_connection=local"
    playbook = [{'hosts': 'all', 'gather_facts': g_facts, 'tasks': [{'debug': {'msg': "test"}}]}]
    if not is_run_async:
        r = run(private_data_dir=tdir,
                inventory=inventory,
                playbook=playbook)
    else:
        _, r = run_async(private_data_dir=tdir,
                         inventory=inventory,
                         playbook=playbook)

    event_types = [x['event'] for x in r.events]
    okay_events = [x for x in filter(lambda x: 'event' in x and x['event'] == 'runner_on_ok',
                                     r.events)]
    assert event_types[0] == 'playbook_on_start'
    assert "playbook_on_play_start" in event_types
    assert "runner_on_ok" in event_types
    assert "playbook_on_stats" in event_types
    assert r.rc == 0
    if not is_run_async:
        assert len(okay_events) == 1
    else:
        assert len(okay_events) == 2

    okay_event = okay_events[0]
    assert "uuid" in okay_event and len(okay_event['uuid']) == 36
    assert "stdout" in okay_event and len(okay_event['stdout']) > 0
    assert "event_data" in okay_event and len(okay_event['event_data']) > 0


def test_async_events():
    test_basic_events(is_run_async=True,g_facts=True)


def test_basic_serializeable():
    tdir = tempfile.mkdtemp()
    r = run(private_data_dir=tdir,
            inventory="localhost ansible_connection=local",
            playbook=[{'hosts': 'all', 'gather_facts': False, 'tasks': [{'debug': {'msg': "test"}}]}])
    events = [x for x in r.events]
    json.dumps(events)


@pytest.mark.skipif(LooseVersion(pkg_resources.get_distribution('ansible').version) < LooseVersion('2.8'),
                    reason="Valid only on Ansible 2.8+")
def test_runner_on_start(rc):
    tdir = tempfile.mkdtemp()
    r = run(private_data_dir=tdir,
            inventory="localhost ansible_connection=local",
            playbook=[{'hosts': 'all', 'gather_facts': False, 'tasks': [{'debug': {'msg': "test"}}]}])
    start_events = [x for x in filter(lambda x: 'event' in x and x['event'] == 'runner_on_start',
                                      r.events)]
    assert len(start_events) == 1


def test_playbook_on_stats_summary_fields(rc):
    tdir = tempfile.mkdtemp()
    r = run(private_data_dir=tdir,
            inventory="localhost ansible_connection=local",
            playbook=[{'hosts': 'all', 'gather_facts': False, 'tasks': [{'debug': {'msg': "test"}}]}])
    stats_events = [x for x in filter(lambda x: 'event' in x and x['event'] == 'playbook_on_stats',
                                      r.events)]
    assert len(stats_events) == 1

    EXPECTED_SUMMARY_FIELDS = ('changed', 'dark', 'failures', 'ignored', 'ok', 'rescued', 'skipped')
    fields = stats_events[0]['event_data'].keys()
    assert set(fields) >= set(EXPECTED_SUMMARY_FIELDS)


def test_include_role_events():
    r = run(
        private_data_dir=os.path.abspath('test/integration'),
        playbook='use_role.yml'
    )
    role_events = [event for event in r.events if event.get('event_data', {}).get('role', '') == "benthomasson.hello_role"]
    assert 'runner_on_ok' in [event['event'] for event in role_events]
    for event in role_events:
        event_data = event['event_data']
        assert not event_data.get('warning', False)  # role use should not contain warnings
        if event['event'] == 'runner_on_ok':
            assert event_data['res']['msg'] == 'Hello world!'
