import json
import pytest

from ansible_runner import defaults, run, run_async


@pytest.mark.test_all_runtimes
@pytest.mark.parametrize('containerized', [True, False])
def test_basic_events(containerized, runtime, tmp_path, is_run_async=False, g_facts=False):

    inventory = 'localhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"'

    playbook = [{'hosts': 'all', 'gather_facts': g_facts, 'tasks': [{'debug': {'msg': "test"}}]}]
    run_args = {'private_data_dir': str(tmp_path),
                'inventory': inventory,
                'envvars': {"ANSIBLE_DEPRECATION_WARNINGS": "False", 'ANSIBLE_PYTHON_INTERPRETER': 'auto_silent'},
                'playbook': playbook}
    if containerized:
        run_args.update({'process_isolation': True,
                         'process_isolation_executable': runtime,
                         'container_image': defaults.default_container_image,
                         'container_volume_mounts': [f'{tmp_path}:{tmp_path}']})

    if not is_run_async:
        r = run(**run_args)
    else:
        thread, r = run_async(**run_args)
        thread.join()  # ensure async run finishes

    event_types = [x['event'] for x in r.events if x['event'] != 'verbose']
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
    assert "parent_uuid" in okay_event and len(okay_event['parent_uuid']) == 36
    assert "stdout" in okay_event and len(okay_event['stdout']) > 0
    assert "start_line" in okay_event and int(okay_event['start_line']) > 0
    assert "end_line" in okay_event and int(okay_event['end_line']) > 0
    assert "event_data" in okay_event and len(okay_event['event_data']) > 0


@pytest.mark.test_all_runtimes
@pytest.mark.parametrize('containerized', [True, False])
def test_async_events(containerized, runtime, tmp_path):
    test_basic_events(containerized, runtime, tmp_path, is_run_async=True, g_facts=True)


def test_basic_serializeable(tmp_path):
    inv = 'localhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"'
    r = run(private_data_dir=str(tmp_path),
            inventory=inv,
            playbook=[{'hosts': 'all', 'gather_facts': False, 'tasks': [{'debug': {'msg': "test"}}]}])
    events = [x for x in r.events]
    json.dumps(events)


def test_event_omission(tmp_path):
    inv = 'localhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"'
    r = run(private_data_dir=str(tmp_path),
            inventory=inv,
            omit_event_data=True,
            playbook=[{'hosts': 'all', 'gather_facts': False, 'tasks': [{'debug': {'msg': "test"}}]}])

    events = []

    for x in r.events:
        if x['event'] == 'verbose':
            continue
        events.append(x)

    assert not any([x['event_data'] for x in events])


def test_event_omission_except_failed(tmp_path):
    inv = 'localhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"'
    r = run(private_data_dir=str(tmp_path),
            inventory=inv,
            only_failed_event_data=True,
            playbook=[{'hosts': 'all', 'gather_facts': False, 'tasks': [{'fail': {'msg': "test"}}]}])

    events = []

    for x in r.events:
        if x['event'] == 'verbose':
            continue
        events.append(x)

    all_event_datas = [x['event_data'] for x in events if x['event_data']]

    assert len(all_event_datas) == 1


def test_runner_on_start(rc, tmp_path):
    r = run(private_data_dir=str(tmp_path),
            inventory='localhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"',
            playbook=[{'hosts': 'all', 'gather_facts': False, 'tasks': [{'debug': {'msg': "test"}}]}])
    start_events = [x for x in filter(lambda x: 'event' in x and x['event'] == 'runner_on_start',
                                      r.events)]
    assert len(start_events) == 1


def test_playbook_on_stats_summary_fields(project_fixtures):
    private_data_dir = project_fixtures / 'host_status'

    res = run(
        private_data_dir=private_data_dir,
        playbook='gen_host_status.yml'
    )
    assert res.rc != 0, res.stdout.read()

    EXPECTED_SUMMARY_FIELDS = ('changed', 'dark', 'failures', 'ignored', 'ok', 'rescued', 'skipped')

    runner_stats = res.stats
    for stat in EXPECTED_SUMMARY_FIELDS:
        assert stat in runner_stats
        assert runner_stats[stat]  # expected at least 1 host in each stat type


def test_include_role_events(project_fixtures):
    r = run(
        private_data_dir=str(project_fixtures / 'use_role'),
        playbook='use_role.yml'
    )
    role_events = [event for event in r.events if event.get('event_data', {}).get('role', '') == "benthomasson.hello_role"]
    assert 'runner_on_ok' in [event['event'] for event in role_events]
    for event in role_events:
        event_data = event['event_data']
        assert not event_data.get('warning', False)  # role use should not contain warnings
        assert 'resolved_role' not in event_data  # should not specify FQCN name if not from collection
        if event['event'] == 'runner_on_ok':
            assert event_data['res']['msg'] == 'Hello world!'
        if event['event'] == 'playbook_on_task_start':
            assert event_data['resolved_action'] == 'ansible.builtin.debug'


def test_include_role_from_collection_events(project_fixtures):
    r = run(
        private_data_dir=str(project_fixtures / 'collection_role'),
        playbook='use_role.yml'
    )
    for event in r.events:
        event_data = event['event_data']
        assert not event_data.get('warning', False)  # role use should not contain warnings
        if event['event'] in ('runner_on_ok', 'playbook_on_task_start', 'runner_on_start'):
            assert event_data['role'] == 'hello'
            assert event_data['resolved_role'] == 'groovy.peanuts.hello'
        if event['event'] == 'runner_on_ok':
            assert event_data['res']['msg'] == 'Hello peanuts!'
        if event['event'] == 'playbook_on_task_start':
            assert event_data['resolved_action'] == 'ansible.builtin.debug'
        if event['event'] == 'playbook_on_stats':
            assert 'resolved_role' not in event_data
            assert 'resolved_action' not in event_data
