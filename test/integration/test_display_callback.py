from __future__ import absolute_import

import json
import os
import yaml
import six

from ansible_runner.interface import init_runner

import pytest

HERE = os.path.abspath(os.path.dirname(__file__))


@pytest.fixture()
def executor(tmp_path, request):
    private_data_dir = tmp_path / 'foo'
    private_data_dir.mkdir()

    playbooks = request.node.callspec.params.get('playbook')
    playbook = list(playbooks.values())[0]
    envvars = request.node.callspec.params.get('envvars')
    if envvars is None:
        envvars = {}
    # warning messages create verbose events and interfere with assertions
    envvars["ANSIBLE_DEPRECATION_WARNINGS"] = "False"
    # python interpreter used is not of much interest, we really want to silence warnings
    envvars['ANSIBLE_PYTHON_INTERPRETER'] = 'auto_silent'

    inventory = 'localhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"'

    r = init_runner(
        private_data_dir=private_data_dir,
        inventory=inventory,
        envvars=envvars,
        playbook=yaml.safe_load(playbook)
    )

    return r


@pytest.mark.parametrize('event', ['playbook_on_start',
                                   'playbook_on_play_start',
                                   'playbook_on_task_start', 'runner_on_ok',
                                   'playbook_on_stats'])
@pytest.mark.parametrize('playbook', [
{'helloworld.yml': '''
- name: Hello World Sample
  connection: local
  hosts: all
  gather_facts: no
  tasks:
    - name: Hello Message
      debug:
        msg: "Hello World!"
'''},  # noqa
{'results_included.yml': '''
- name: Run module which generates results list
  connection: local
  hosts: all
  gather_facts: no
  vars:
    results: ['foo', 'bar']
  tasks:
    - name: Generate results list
      debug:
        var: results
'''}  # noqa
], ids=['helloworld.yml', 'results_included.yml'])
@pytest.mark.parametrize('envvars', [
    {'ANSIBLE_CALLBACK_PLUGINS': os.path.join(HERE, 'callback')},
    {'ANSIBLE_CALLBACK_PLUGINS': ''}],
    ids=['local-callback-plugin', 'no-callback-plugin']
)
def test_callback_plugin_receives_events(executor, event, playbook, envvars):
    executor.run()
    assert len(list(executor.events))
    assert event in [task['event'] for task in executor.events]


@pytest.mark.parametrize('playbook', [
{'no_log_on_ok.yml': '''
- name: args should not be logged when task-level no_log is set
  connection: local
  hosts: all
  gather_facts: no
  tasks:
    - shell: echo "SENSITIVE"
      no_log: true
'''},  # noqa
{'no_log_on_fail.yml': '''
- name: failed args should not be logged when task-level no_log is set
  connection: local
  hosts: all
  gather_facts: no
  tasks:
    - shell: echo "SENSITIVE"
      no_log: true
      failed_when: true
      ignore_errors: true
'''},  # noqa
{'no_log_on_skip.yml': '''
- name: skipped task args should be suppressed with no_log
  connection: local
  hosts: all
  gather_facts: no
  tasks:
    - shell: echo "SENSITIVE"
      no_log: true
      when: false
'''},  # noqa
{'no_log_on_play.yml': '''
- name: args should not be logged when play-level no_log set
  connection: local
  hosts: all
  gather_facts: no
  no_log: true
  tasks:
      - shell: echo "SENSITIVE"
'''},  # noqa
{'async_no_log.yml': '''
- name: async task args should suppressed with no_log
  connection: local
  hosts: all
  gather_facts: no
  no_log: true
  tasks:
    - async: 10
      poll: 1
      shell: echo "SENSITIVE"
      no_log: true
'''},  # noqa
{'with_items.yml': '''
- name: with_items tasks should be suppressed with no_log
  connection: local
  hosts: all
  gather_facts: no
  tasks:
      - shell: echo {{ item }}
        no_log: true
        with_items: [ "SENSITIVE", "SENSITIVE-SKIPPED", "SENSITIVE-FAILED" ]
        when: item != "SENSITIVE-SKIPPED"
        failed_when: item == "SENSITIVE-FAILED"
        ignore_errors: yes
'''},  # noqa, NOTE: with_items will be deprecated in 2.9
{'loop.yml': '''
- name: loop tasks should be suppressed with no_log
  connection: local
  hosts: all
  gather_facts: no
  tasks:
      - shell: echo {{ item }}
        no_log: true
        loop: [ "SENSITIVE", "SENSITIVE-SKIPPED", "SENSITIVE-FAILED" ]
        when: item != "SENSITIVE-SKIPPED"
        failed_when: item == "SENSITIVE-FAILED"
        ignore_errors: yes
'''},  # noqa
])
def test_callback_plugin_no_log_filters(executor, playbook):
    executor.run()
    assert len(list(executor.events))
    assert 'SENSITIVE' not in json.dumps(list(executor.events))


@pytest.mark.parametrize('playbook', [
{'no_log_on_ok.yml': '''
- name: args should not be logged when no_log is set at the task or module level
  connection: local
  hosts: all
  gather_facts: no
  tasks:
    - shell: echo "PUBLIC"
    - shell: echo "PRIVATE"
      no_log: true
    - uri: url=https://example.org url_username="PUBLIC" url_password="PRIVATE"
'''},  # noqa
])
def test_callback_plugin_task_args_leak(executor, playbook):
    executor.run()
    events = list(executor.events)
    assert events[0]['event'] == 'playbook_on_start'
    assert events[1]['event'] == 'playbook_on_play_start'

    # task 1
    assert events[2]['event'] == 'playbook_on_task_start'
    assert events[3]['event'] == 'runner_on_start'
    assert events[4]['event'] == 'runner_on_ok'

    # task 2 no_log=True
    assert events[5]['event'] == 'playbook_on_task_start'
    assert events[6]['event'] == 'runner_on_start'
    assert events[7]['event'] == 'runner_on_ok'
    assert 'PUBLIC' in json.dumps(events), events
    for event in events:
        assert 'PRIVATE' not in json.dumps(event), event
    # make sure playbook was successful, so all tasks were hit
    assert not events[-1]['event_data']['failures'], 'Unexpected playbook execution failure'


@pytest.mark.parametrize(
    "playbook",
    [
        {
            "simple.yml": """
- name: simpletask
  connection: local
  hosts: all
  gather_facts: no
  tasks:
    - shell: echo "resolved actions test!"
"""
        },  # noqa
    ],
)
def test_resolved_actions(executor, playbook, skipif_pre_ansible212):
    executor.run()
    events = list(executor.events)

    # task 1
    assert events[2]["event"] == "playbook_on_task_start"
    assert "resolved_action" in events[2]["event_data"]
    assert events[2]["event_data"]["resolved_action"] == "ansible.builtin.shell"


@pytest.mark.parametrize("playbook", [
{'loop_with_no_log.yml': '''
- name: playbook variable should not be overwritten when using no log
  connection: local
  hosts: all
  gather_facts: no
  tasks:
    - command: "{{ item }}"
      register: command_register
      no_log: True
      with_items:
        - "echo helloworld!"
    - debug: msg="{{ command_register.results|map(attribute='stdout')|list }}"
'''},  # noqa
])
def test_callback_plugin_censoring_does_not_overwrite(executor, playbook):
    executor.run()
    events = list(executor.events)
    assert events[0]['event'] == 'playbook_on_start'
    assert events[1]['event'] == 'playbook_on_play_start'

    # task 1
    assert events[2]['event'] == 'playbook_on_task_start'
    # Ordering of task and item events may differ randomly
    assert set(['runner_on_start', 'runner_item_on_ok', 'runner_on_ok']) == set([data['event'] for data in events[3:6]])

    # task 2 no_log=True
    assert events[6]['event'] == 'playbook_on_task_start'
    assert events[7]['event'] == 'runner_on_start'
    assert events[8]['event'] == 'runner_on_ok'
    assert 'helloworld!' in events[8]['event_data']['res']['msg']


@pytest.mark.parametrize('playbook', [
{'strip_env_vars.yml': '''
- name: sensitive environment variables should be stripped from events
  connection: local
  hosts: all
  tasks:
    - shell: echo "Hello, World!"
'''},  # noqa
])
def test_callback_plugin_strips_task_environ_variables(executor, playbook):
    executor.run()
    assert len(list(executor.events))
    for event in list(executor.events):
        assert os.environ['PATH'] not in json.dumps(event)


@pytest.mark.parametrize('playbook', [
{'custom_set_stat.yml': '''
- name: custom set_stat calls should persist to the local disk so awx can save them
  connection: local
  hosts: all
  tasks:
    - set_stats:
        data:
          foo: "bar"
'''},  # noqa
])
def test_callback_plugin_saves_custom_stats(executor, playbook):
    executor.run()
    for event in executor.events:
        event_data = event.get('event_data', {})
        if 'artifact_data' in event_data:
            assert event_data['artifact_data'] == {'foo': 'bar'}
            break
    else:
        raise Exception('Did not find expected artifact data in event data')


@pytest.mark.parametrize('playbook', [
{'handle_playbook_on_notify.yml': '''
- name: handle playbook_on_notify events properly
  connection: local
  hosts: all
  handlers:
    - name: my_handler
      debug: msg="My Handler"
  tasks:
    - debug: msg="My Task"
      changed_when: true
      notify:
        - my_handler
'''},  # noqa
])
def test_callback_plugin_records_notify_events(executor, playbook):
    executor.run()
    assert len(list(executor.events))
    notify_events = [x for x in executor.events if x['event'] == 'playbook_on_notify']
    assert len(notify_events) == 1
    assert notify_events[0]['event_data']['handler'] == 'my_handler'
    assert notify_events[0]['event_data']['host'] == 'localhost'
    assert notify_events[0]['event_data']['task'] == 'debug'


@pytest.mark.parametrize('playbook', [
{'no_log_module_with_var.yml': '''
- name: ensure that module-level secrets are redacted
  connection: local
  hosts: all
  vars:
    - pw: SENSITIVE
  tasks:
    - uri:
        url: https://example.org
        url_username: john-jacob-jingleheimer-schmidt
        url_password: "{{ pw }}"
'''},  # noqa
])
def test_module_level_no_log(executor, playbook):
    # It's possible for `no_log=True` to be defined at the _module_ level,
    # e.g., for the URI module password parameter
    # This test ensures that we properly redact those
    executor.run()
    assert len(list(executor.events))
    assert 'john-jacob-jingleheimer-schmidt' in json.dumps(list(executor.events))
    assert 'SENSITIVE' not in json.dumps(list(executor.events))


def test_output_when_given_invalid_playbook(tmp_path):
    # As shown in the following issue:
    #
    #   https://github.com/ansible/ansible-runner/issues/29
    #
    # There was a lack of output by runner when a playbook that doesn't exist
    # is provided.  This was fixed in this PR:
    #
    #   https://github.com/ansible/ansible-runner/pull/34
    #
    # But no test validated it.  This does that.
    private_data_dir = str(tmp_path)
    executor = init_runner(
        private_data_dir=private_data_dir,
        inventory='localhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"',
        envvars={"ANSIBLE_DEPRECATION_WARNINGS": "False"},
        playbook=os.path.join(private_data_dir, 'fake_playbook.yml')
    )

    executor.run()
    stdout = executor.stdout.read()
    assert "ERROR! the playbook:" in stdout
    assert "could not be found" in stdout


def test_output_when_given_non_playbook_script(tmp_path):
    # As shown in the following pull request:
    #
    #   https://github.com/ansible/ansible-runner/pull/256
    #
    # This ports some functionality that previously lived in awx and allows raw
    # lines of stdout to be treated as event lines.
    #
    # As mentioned in the pull request as well, there were no specs added, and
    # this is a retro-active test based on the sample repo provided in the PR:
    #
    #   https://github.com/AlanCoding/ansible-runner-examples/tree/master/non_playbook/sleep_with_writes
    private_data_dir = str(tmp_path)
    with open(os.path.join(private_data_dir, "args"), 'w') as args_file:
        args_file.write("bash sleep_and_write.sh\n")
    with open(os.path.join(private_data_dir, "sleep_and_write.sh"), 'w') as script_file:
        script_file.write("echo 'hi world'\nsleep 0.5\necho 'goodbye world'\n")

    # Update the settings to make this test a bit faster :)
    os.mkdir(os.path.join(private_data_dir, "env"))
    with open(os.path.join(private_data_dir, "env", "settings"), 'w') as settings_file:
        settings_file.write("pexpect_timeout: 0.2")

    executor = init_runner(
        private_data_dir=private_data_dir,
        inventory='localhost ansible_connection=local ansible_python_interpreter="{{ ansible_playbook_python }}"',
        envvars={"ANSIBLE_DEPRECATION_WARNINGS": "False"}
    )

    executor.run()
    stdout = executor.stdout.readlines()
    assert stdout[0].strip() == "hi world"
    assert stdout[1].strip() == "goodbye world"

    events = list(executor.events)

    assert len(events) == 2
    assert events[0]['event'] == 'verbose'
    assert events[0]['stdout'] == 'hi world'
    assert events[1]['event'] == 'verbose'
    assert events[1]['stdout'] == 'goodbye world'


@pytest.mark.parametrize('playbook', [
{'listvars.yml': '''
- name: List Variables
  connection: local
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Print a lot of lines
      debug:
        msg: "{{ ('F' * 150) | list }}"
'''},  # noqa
])
def test_large_stdout_parsing_when_using_json_output(executor, playbook):
    # When the json flag is used, it is possible to output more data than
    # pexpect's maxread default of 2000 characters.  As a result, if not
    # handled properly, the stdout can end up being corrupted with partial
    # non-event matches with raw "non-json" lines being intermixed with json
    # ones.
    #
    # This tests to confirm we don't pollute the stdout output with non-json
    # lines when a single event has a lot of output.
    if six.PY2:
        pytest.skip('Ansible in python2 uses different syntax.')
    executor.config.env['ANSIBLE_NOCOLOR'] = str(True)
    executor.run()
    text = executor.stdout.read()
    assert text.count('"F"') == 150
