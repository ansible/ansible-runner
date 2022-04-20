# Copyright (c) 2016 Ansible by Red Hat, Inc.
#
# This file is part of Ansible Tower, but depends on code imported from Ansible.
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import (absolute_import, division, print_function)


DOCUMENTATION = '''
    callback: awx_display
    short_description: Playbook event dispatcher for ansible-runner
    version_added: "2.0"
    description:
        - This callback is necessary for ansible-runner to work
    type: stdout
    extends_documentation_fragment:
      - default_callback
    requirements:
      - Set as stdout in config
'''

# Python
import json
import stat
import multiprocessing
import threading
import base64
import functools
import collections
import contextlib
import datetime
import os
import sys
import uuid
from copy import copy

# Ansible
from ansible import constants as C
from ansible.plugins.loader import callback_loader
from ansible.utils.display import Display

IS_ADHOC = os.getenv('AD_HOC_COMMAND_ID', False)

# Dynamically construct base classes for our callback module, to support custom stdout callbacks.
if os.getenv('ORIGINAL_STDOUT_CALLBACK'):
    default_stdout_callback = os.getenv('ORIGINAL_STDOUT_CALLBACK')
elif IS_ADHOC:
    default_stdout_callback = 'minimal'
else:
    default_stdout_callback = 'default'

DefaultCallbackModule = callback_loader.get(default_stdout_callback).__class__

CENSORED = "the output has been hidden due to the fact that 'no_log: true' was specified for this result"


def current_time():
    return datetime.datetime.utcnow()


# use a custom JSON serializer so we can properly handle !unsafe and !vault
# objects that may exist in events emitted by the callback plugin
# see: https://github.com/ansible/ansible/pull/38759
class AnsibleJSONEncoderLocal(json.JSONEncoder):
    '''
    The class AnsibleJSONEncoder exists in Ansible core for this function
    this performs a mostly identical function via duck typing
    '''

    def default(self, o):
        '''
        Returns JSON-valid representation for special Ansible python objects
        which including vault objects and datetime objects
        '''
        if getattr(o, 'yaml_tag', None) == '!vault':
            encrypted_form = o._ciphertext
            if isinstance(encrypted_form, bytes):
                encrypted_form = encrypted_form.decode('utf-8')
            return {'__ansible_vault': encrypted_form}
        elif isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        return super(AnsibleJSONEncoderLocal, self).default(o)


class IsolatedFileWrite:
    '''
    Class that will write partial event data to a file
    '''

    def __init__(self):
        self.private_data_dir = os.getenv('AWX_ISOLATED_DATA_DIR')

    def set(self, key, value):
        # Strip off the leading key identifying characters :1:ev-
        event_uuid = key[len(':1:ev-'):]
        # Write data in a staging area and then atomic move to pickup directory
        filename = '{}-partial.json'.format(event_uuid)
        if not os.path.exists(os.path.join(self.private_data_dir, 'job_events')):
            os.mkdir(os.path.join(self.private_data_dir, 'job_events'), 0o700)
        dropoff_location = os.path.join(self.private_data_dir, 'job_events', filename)
        write_location = '.'.join([dropoff_location, 'tmp'])
        partial_data = json.dumps(value, cls=AnsibleJSONEncoderLocal)
        with os.fdopen(os.open(write_location, os.O_WRONLY | os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR), 'w') as f:
            f.write(partial_data)
        os.rename(write_location, dropoff_location)


class EventContext(object):
    '''
    Store global and local (per thread/process) data associated with callback
    events and other display output methods.
    '''

    def __init__(self):
        self.display_lock = multiprocessing.RLock()
        self._local = threading.local()
        if os.getenv('AWX_ISOLATED_DATA_DIR', False):
            self.cache = IsolatedFileWrite()

    def add_local(self, **kwargs):
        tls = vars(self._local)
        ctx = tls.setdefault('_ctx', {})
        ctx.update(kwargs)

    def remove_local(self, **kwargs):
        for key in kwargs.keys():
            self._local._ctx.pop(key, None)

    @contextlib.contextmanager
    def set_local(self, **kwargs):
        try:
            self.add_local(**kwargs)
            yield
        finally:
            self.remove_local(**kwargs)

    def get_local(self):
        return getattr(getattr(self, '_local', None), '_ctx', {})

    def add_global(self, **kwargs):
        if not hasattr(self, '_global_ctx'):
            self._global_ctx = {}
        self._global_ctx.update(kwargs)

    def remove_global(self, **kwargs):
        if hasattr(self, '_global_ctx'):
            for key in kwargs.keys():
                self._global_ctx.pop(key, None)

    @contextlib.contextmanager
    def set_global(self, **kwargs):
        try:
            self.add_global(**kwargs)
            yield
        finally:
            self.remove_global(**kwargs)

    def get_global(self):
        return getattr(self, '_global_ctx', {})

    def get(self):
        ctx = {}
        ctx.update(self.get_global())
        ctx.update(self.get_local())
        return ctx

    def get_begin_dict(self):
        omit_event_data = os.getenv("RUNNER_OMIT_EVENTS", "False").lower() == "true"
        include_only_failed_event_data = os.getenv("RUNNER_ONLY_FAILED_EVENTS", "False").lower() == "true"
        event_data = self.get()
        event = event_data.pop('event', None)
        if not event:
            event = 'verbose'
            for key in ('debug', 'verbose', 'deprecated', 'warning', 'system_warning', 'error'):
                if event_data.get(key, False):
                    event = key
                    break
        event_dict = dict(event=event)
        should_process_event_data = (include_only_failed_event_data and event in ('runner_on_failed', 'runner_on_async_failed', 'runner_on_item_failed')) \
            or not include_only_failed_event_data
        if os.getenv('JOB_ID', ''):
            event_dict['job_id'] = int(os.getenv('JOB_ID', '0'))
        if os.getenv('AD_HOC_COMMAND_ID', ''):
            event_dict['ad_hoc_command_id'] = int(os.getenv('AD_HOC_COMMAND_ID', '0'))
        if os.getenv('PROJECT_UPDATE_ID', ''):
            event_dict['project_update_id'] = int(os.getenv('PROJECT_UPDATE_ID', '0'))
        event_dict['pid'] = event_data.get('pid', os.getpid())
        event_dict['uuid'] = event_data.get('uuid', str(uuid.uuid4()))
        event_dict['created'] = event_data.get('created', datetime.datetime.utcnow().isoformat())
        if not event_data.get('parent_uuid', None):
            for key in ('task_uuid', 'play_uuid', 'playbook_uuid'):
                parent_uuid = event_data.get(key, None)
                if parent_uuid and parent_uuid != event_data.get('uuid', None):
                    event_dict['parent_uuid'] = parent_uuid
                    break
        else:
            event_dict['parent_uuid'] = event_data.get('parent_uuid', None)
        if "verbosity" in event_data.keys():
            event_dict["verbosity"] = event_data.pop("verbosity")
        if not omit_event_data and should_process_event_data:
            max_res = int(os.getenv("MAX_EVENT_RES", 700000))
            if event not in ('playbook_on_stats',) and "res" in event_data and len(str(event_data['res'])) > max_res:
                event_data['res'] = {}
        else:
            event_data = dict()
        event_dict['event_data'] = event_data
        return event_dict

    def get_end_dict(self):
        return {}

    def dump(self, fileobj, data, max_width=78, flush=False):
        b64data = base64.b64encode(json.dumps(data).encode('utf-8')).decode()
        with self.display_lock:
            # pattern corresponding to OutputEventFilter expectation
            fileobj.write(u'\x1b[K')
            for offset in range(0, len(b64data), max_width):
                chunk = b64data[offset:offset + max_width]
                escaped_chunk = u'{}\x1b[{}D'.format(chunk, len(chunk))
                fileobj.write(escaped_chunk)
            fileobj.write(u'\x1b[K')
            if flush:
                fileobj.flush()

    def dump_begin(self, fileobj):
        begin_dict = self.get_begin_dict()
        self.cache.set(":1:ev-{}".format(begin_dict['uuid']), begin_dict)
        self.dump(fileobj, {'uuid': begin_dict['uuid']})

    def dump_end(self, fileobj):
        self.dump(fileobj, self.get_end_dict(), flush=True)


event_context = EventContext()


def with_context(**context):
    global event_context

    def wrap(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with event_context.set_local(**context):
                return f(*args, **kwargs)
        return wrapper
    return wrap


for attr in dir(Display):
    if attr.startswith('_') or 'cow' in attr or 'prompt' in attr:
        continue
    if attr in ('display', 'v', 'vv', 'vvv', 'vvvv', 'vvvvv', 'vvvvvv', 'verbose'):
        continue
    if not callable(getattr(Display, attr)):
        continue
    setattr(Display, attr, with_context(**{attr: True})(getattr(Display, attr)))


def with_verbosity(f):
    global event_context

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        host = args[2] if len(args) >= 3 else kwargs.get('host', None)
        caplevel = args[3] if len(args) >= 4 else kwargs.get('caplevel', 2)
        context = dict(verbose=True, verbosity=(caplevel + 1))
        if host is not None:
            context['remote_addr'] = host
        with event_context.set_local(**context):
            return f(*args, **kwargs)
    return wrapper


Display.verbose = with_verbosity(Display.verbose)


def display_with_context(f):

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        log_only = args[5] if len(args) >= 6 else kwargs.get('log_only', False)
        stderr = args[3] if len(args) >= 4 else kwargs.get('stderr', False)
        event_uuid = event_context.get().get('uuid', None)
        with event_context.display_lock:
            # If writing only to a log file or there is already an event UUID
            # set (from a callback module method), skip dumping the event data.
            if log_only or event_uuid:
                return f(*args, **kwargs)
            try:
                fileobj = sys.stderr if stderr else sys.stdout
                event_context.add_local(uuid=str(uuid.uuid4()))
                event_context.dump_begin(fileobj)
                return f(*args, **kwargs)
            finally:
                event_context.dump_end(fileobj)
                event_context.remove_local(uuid=None)

    return wrapper


Display.display = display_with_context(Display.display)


class CallbackModule(DefaultCallbackModule):
    '''
    Callback module for logging ansible/ansible-playbook events.
    '''

    CALLBACK_NAME = 'awx_display'

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'stdout'

    # These events should never have an associated play.
    EVENTS_WITHOUT_PLAY = [
        'playbook_on_start',
        'playbook_on_stats',
    ]

    # These events should never have an associated task.
    EVENTS_WITHOUT_TASK = EVENTS_WITHOUT_PLAY + [
        'playbook_on_setup',
        'playbook_on_notify',
        'playbook_on_import_for_host',
        'playbook_on_not_import_for_host',
        'playbook_on_no_hosts_matched',
        'playbook_on_no_hosts_remaining',
    ]

    def __init__(self):
        super(CallbackModule, self).__init__()
        self._host_start = {}
        self.task_uuids = set()
        self.duplicate_task_counts = collections.defaultdict(lambda: 1)

        self.play_uuids = set()
        self.duplicate_play_counts = collections.defaultdict(lambda: 1)

    @contextlib.contextmanager
    def capture_event_data(self, event, **event_data):
        event_data.setdefault('uuid', str(uuid.uuid4()))

        if event not in self.EVENTS_WITHOUT_TASK:
            task = event_data.pop('task', None)
        else:
            task = None

        if event_data.get('res'):
            if event_data['res'].get('_ansible_no_log', False):
                event_data['res'] = {'censored': CENSORED}
            if event_data['res'].get('results', []):
                event_data['res']['results'] = copy(event_data['res']['results'])
            for i, item in enumerate(event_data['res'].get('results', [])):
                if isinstance(item, dict) and item.get('_ansible_no_log', False):
                    event_data['res']['results'][i] = {'censored': CENSORED}

        with event_context.display_lock:
            try:
                event_context.add_local(event=event, **event_data)
                if task:
                    self.set_task(task, local=True)
                event_context.dump_begin(sys.stdout)
                yield
            finally:
                event_context.dump_end(sys.stdout)
                if task:
                    self.clear_task(local=True)
                event_context.remove_local(event=None, **event_data)

    def set_playbook(self, playbook):
        # NOTE: Ansible doesn't generate a UUID for playbook_on_start so do it for them.
        self.playbook_uuid = str(uuid.uuid4())
        file_name = getattr(playbook, '_file_name', '???')
        event_context.add_global(playbook=file_name, playbook_uuid=self.playbook_uuid)
        self.clear_play()

    def set_play(self, play):
        if hasattr(play, 'hosts'):
            if isinstance(play.hosts, list):
                pattern = ','.join(play.hosts)
            else:
                pattern = play.hosts
        else:
            pattern = ''
        name = play.get_name().strip() or pattern
        event_context.add_global(play=name, play_uuid=str(play._uuid), play_pattern=pattern)
        self.clear_task()

    def clear_play(self):
        event_context.remove_global(play=None, play_uuid=None, play_pattern=None)
        self.clear_task()

    def set_task(self, task, local=False):
        self.clear_task(local)
        # FIXME: Task is "global" unless using free strategy!
        task_ctx = dict(
            task=(task.name or task.action),
            task_uuid=str(task._uuid),
            task_action=task.action,
            resolved_action=getattr(task, 'resolved_action', task.action),
            task_args='',
        )
        try:
            task_ctx['task_path'] = task.get_path()
        except AttributeError:
            pass
        if C.DISPLAY_ARGS_TO_STDOUT:
            if task.no_log:
                task_ctx['task_args'] = "the output has been hidden due to the fact that 'no_log: true' was specified for this result"
            else:
                task_args = ', '.join(('%s=%s' % a for a in task.args.items()))
                task_ctx['task_args'] = task_args
        if getattr(task, '_role', None):
            task_role = task._role._role_name
            if hasattr(task._role, 'get_name'):
                resolved_role = task._role.get_name()
                if resolved_role != task_role:
                    task_ctx['resolved_role'] = resolved_role
        else:
            task_role = getattr(task, 'role_name', '')
        if task_role:
            task_ctx['role'] = task_role
        if local:
            event_context.add_local(**task_ctx)
        else:
            event_context.add_global(**task_ctx)

    def clear_task(self, local=False):
        task_ctx = dict(
            task=None, task_path=None, task_uuid=None, task_action=None, task_args=None, resolved_action=None,
            role=None, resolved_role=None
        )
        if local:
            event_context.remove_local(**task_ctx)
        else:
            event_context.remove_global(**task_ctx)

    def v2_playbook_on_start(self, playbook):
        self.set_playbook(playbook)
        event_data = dict(
            uuid=self.playbook_uuid,
        )
        with self.capture_event_data('playbook_on_start', **event_data):
            super(CallbackModule, self).v2_playbook_on_start(playbook)

    def v2_playbook_on_vars_prompt(self, varname, private=True, prompt=None,
                                   encrypt=None, confirm=False, salt_size=None,
                                   salt=None, default=None, unsafe=None):
        event_data = dict(
            varname=varname,
            private=private,
            prompt=prompt,
            encrypt=encrypt,
            confirm=confirm,
            salt_size=salt_size,
            salt=salt,
            default=default,
            unsafe=unsafe,
        )
        with self.capture_event_data('playbook_on_vars_prompt', **event_data):
            super(CallbackModule, self).v2_playbook_on_vars_prompt(
                varname, private, prompt, encrypt, confirm, salt_size, salt,
                default,
            )

    def v2_playbook_on_include(self, included_file):
        event_data = dict(
            included_file=included_file._filename if included_file is not None else None,
        )
        with self.capture_event_data('playbook_on_include', **event_data):
            super(CallbackModule, self).v2_playbook_on_include(included_file)

    def v2_playbook_on_play_start(self, play):
        if IS_ADHOC:
            return
        play_uuid = str(play._uuid)
        if play_uuid in self.play_uuids:
            # When this play UUID repeats, it means the play is using the
            # free strategy (or serial:1) so different hosts may be running
            # different tasks within a play (where duplicate UUIDS are common).
            #
            # When this is the case, modify the UUID slightly to append
            # a counter so we can still _track_ duplicate events, but also
            # avoid breaking the display in these scenarios.
            self.duplicate_play_counts[play_uuid] += 1

            play_uuid = '_'.join([
                play_uuid,
                str(self.duplicate_play_counts[play_uuid])
            ])
        self.play_uuids.add(play_uuid)
        play._uuid = play_uuid

        self.set_play(play)
        if hasattr(play, 'hosts'):
            if isinstance(play.hosts, list):
                pattern = ','.join(play.hosts)
            else:
                pattern = play.hosts
        else:
            pattern = ''
        name = play.get_name().strip() or pattern
        event_data = dict(
            name=name,
            pattern=pattern,
            uuid=str(play._uuid),
        )
        with self.capture_event_data('playbook_on_play_start', **event_data):
            super(CallbackModule, self).v2_playbook_on_play_start(play)

    def v2_playbook_on_import_for_host(self, result, imported_file):
        # NOTE: Not used by Ansible 2.x.
        with self.capture_event_data('playbook_on_import_for_host'):
            super(CallbackModule, self).v2_playbook_on_import_for_host(result, imported_file)

    def v2_playbook_on_not_import_for_host(self, result, missing_file):
        # NOTE: Not used by Ansible 2.x.
        with self.capture_event_data('playbook_on_not_import_for_host'):
            super(CallbackModule, self).v2_playbook_on_not_import_for_host(result, missing_file)

    def v2_playbook_on_setup(self):
        # NOTE: Not used by Ansible 2.x.
        with self.capture_event_data('playbook_on_setup'):
            super(CallbackModule, self).v2_playbook_on_setup()

    def v2_playbook_on_task_start(self, task, is_conditional):
        if IS_ADHOC:
            self.set_task(task)
            return
        # FIXME: Flag task path output as vv.
        task_uuid = str(task._uuid)
        if task_uuid in self.task_uuids:
            # When this task UUID repeats, it means the play is using the
            # free strategy (or serial:1) so different hosts may be running
            # different tasks within a play (where duplicate UUIDS are common).
            #
            # When this is the case, modify the UUID slightly to append
            # a counter so we can still _track_ duplicate events, but also
            # avoid breaking the display in these scenarios.
            self.duplicate_task_counts[task_uuid] += 1

            task_uuid = '_'.join([
                task_uuid,
                str(self.duplicate_task_counts[task_uuid])
            ])
        self.task_uuids.add(task_uuid)
        self.set_task(task)
        event_data = dict(
            task=task,
            name=task.get_name(),
            is_conditional=is_conditional,
            uuid=task_uuid,
        )
        with self.capture_event_data('playbook_on_task_start', **event_data):
            super(CallbackModule, self).v2_playbook_on_task_start(task, is_conditional)

    def v2_playbook_on_cleanup_task_start(self, task):
        # NOTE: Not used by Ansible 2.x.
        self.set_task(task)
        event_data = dict(
            task=task,
            name=task.get_name(),
            uuid=str(task._uuid),
            is_conditional=True,
        )
        with self.capture_event_data('playbook_on_task_start', **event_data):
            super(CallbackModule, self).v2_playbook_on_cleanup_task_start(task)

    def v2_playbook_on_handler_task_start(self, task):
        # NOTE: Re-using playbook_on_task_start event for this v2-specific
        # event, but setting is_conditional=True, which is how v1 identified a
        # task run as a handler.
        self.set_task(task)
        event_data = dict(
            task=task,
            name=task.get_name(),
            uuid=str(task._uuid),
            is_conditional=True,
        )
        with self.capture_event_data('playbook_on_task_start', **event_data):
            super(CallbackModule, self).v2_playbook_on_handler_task_start(task)

    def v2_playbook_on_no_hosts_matched(self):
        with self.capture_event_data('playbook_on_no_hosts_matched'):
            super(CallbackModule, self).v2_playbook_on_no_hosts_matched()

    def v2_playbook_on_no_hosts_remaining(self):
        with self.capture_event_data('playbook_on_no_hosts_remaining'):
            super(CallbackModule, self).v2_playbook_on_no_hosts_remaining()

    def v2_playbook_on_notify(self, handler, host):
        # NOTE: Not used by Ansible < 2.5.
        event_data = dict(
            host=host.get_name(),
            handler=handler.get_name(),
        )
        with self.capture_event_data('playbook_on_notify', **event_data):
            super(CallbackModule, self).v2_playbook_on_notify(handler, host)

    '''
    ansible_stats is, retroactively, added in 2.2
    '''
    def v2_playbook_on_stats(self, stats):
        self.clear_play()
        # FIXME: Add count of plays/tasks.
        event_data = dict(
            changed=stats.changed,
            dark=stats.dark,
            failures=stats.failures,
            ignored=getattr(stats, 'ignored', 0),
            ok=stats.ok,
            processed=stats.processed,
            rescued=getattr(stats, 'rescued', 0),
            skipped=stats.skipped,
            artifact_data=stats.custom.get('_run', {}) if hasattr(stats, 'custom') else {}
        )

        with self.capture_event_data('playbook_on_stats', **event_data):
            super(CallbackModule, self).v2_playbook_on_stats(stats)

    @staticmethod
    def _get_event_loop(task):
        if hasattr(task, 'loop_with'):  # Ansible >=2.5
            return task.loop_with
        elif hasattr(task, 'loop'):  # Ansible <2.4
            return task.loop
        return None

    def _get_result_timing_data(self, result):
        host_start = self._host_start.get(result._host.get_name())
        if host_start:
            end_time = current_time()
            return host_start, end_time, (end_time - host_start).total_seconds()
        return None, None, None

    def v2_runner_on_ok(self, result):
        # FIXME: Display detailed results or not based on verbosity.

        # strip environment vars from the job event; it already exists on the
        # job and sensitive values are filtered there
        if result._task.action in ('setup', 'gather_facts'):
            result._result.get('ansible_facts', {}).pop('ansible_env', None)

        host_start, end_time, duration = self._get_result_timing_data(result)
        event_data = dict(
            host=result._host.get_name(),
            remote_addr=result._host.address,
            task=result._task,
            res=result._result,
            start=host_start,
            end=end_time,
            duration=duration,
            event_loop=self._get_event_loop(result._task),
        )
        with self.capture_event_data('runner_on_ok', **event_data):
            super(CallbackModule, self).v2_runner_on_ok(result)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        # FIXME: Add verbosity for exception/results output.
        host_start, end_time, duration = self._get_result_timing_data(result)
        event_data = dict(
            host=result._host.get_name(),
            remote_addr=result._host.address,
            res=result._result,
            task=result._task,
            start=host_start,
            end=end_time,
            duration=duration,
            ignore_errors=ignore_errors,
            event_loop=self._get_event_loop(result._task),
        )
        with self.capture_event_data('runner_on_failed', **event_data):
            super(CallbackModule, self).v2_runner_on_failed(result, ignore_errors)

    def v2_runner_on_skipped(self, result):
        host_start, end_time, duration = self._get_result_timing_data(result)
        event_data = dict(
            host=result._host.get_name(),
            remote_addr=result._host.address,
            task=result._task,
            start=host_start,
            end=end_time,
            duration=duration,
            event_loop=self._get_event_loop(result._task),
        )
        with self.capture_event_data('runner_on_skipped', **event_data):
            super(CallbackModule, self).v2_runner_on_skipped(result)

    def v2_runner_on_unreachable(self, result):
        host_start, end_time, duration = self._get_result_timing_data(result)
        event_data = dict(
            host=result._host.get_name(),
            remote_addr=result._host.address,
            task=result._task,
            start=host_start,
            end=end_time,
            duration=duration,
            res=result._result,
        )
        with self.capture_event_data('runner_on_unreachable', **event_data):
            super(CallbackModule, self).v2_runner_on_unreachable(result)

    def v2_runner_on_no_hosts(self, task):
        # NOTE: Not used by Ansible 2.x.
        event_data = dict(
            task=task,
        )
        with self.capture_event_data('runner_on_no_hosts', **event_data):
            super(CallbackModule, self).v2_runner_on_no_hosts(task)

    def v2_runner_on_async_poll(self, result):
        # NOTE: Not used by Ansible 2.x.
        event_data = dict(
            host=result._host.get_name(),
            task=result._task,
            res=result._result,
            jid=result._result.get('ansible_job_id'),
        )
        with self.capture_event_data('runner_on_async_poll', **event_data):
            super(CallbackModule, self).v2_runner_on_async_poll(result)

    def v2_runner_on_async_ok(self, result):
        # NOTE: Not used by Ansible 2.x.
        event_data = dict(
            host=result._host.get_name(),
            task=result._task,
            res=result._result,
            jid=result._result.get('ansible_job_id'),
        )
        with self.capture_event_data('runner_on_async_ok', **event_data):
            super(CallbackModule, self).v2_runner_on_async_ok(result)

    def v2_runner_on_async_failed(self, result):
        # NOTE: Not used by Ansible 2.x.
        event_data = dict(
            host=result._host.get_name(),
            task=result._task,
            res=result._result,
            jid=result._result.get('ansible_job_id'),
        )
        with self.capture_event_data('runner_on_async_failed', **event_data):
            super(CallbackModule, self).v2_runner_on_async_failed(result)

    def v2_runner_on_file_diff(self, result, diff):
        # NOTE: Not used by Ansible 2.x.
        event_data = dict(
            host=result._host.get_name(),
            task=result._task,
            diff=diff,
        )
        with self.capture_event_data('runner_on_file_diff', **event_data):
            super(CallbackModule, self).v2_runner_on_file_diff(result, diff)

    def v2_on_file_diff(self, result):
        # NOTE: Logged as runner_on_file_diff.
        event_data = dict(
            host=result._host.get_name(),
            task=result._task,
            diff=result._result.get('diff'),
        )
        with self.capture_event_data('runner_on_file_diff', **event_data):
            super(CallbackModule, self).v2_on_file_diff(result)

    def v2_runner_item_on_ok(self, result):
        event_data = dict(
            host=result._host.get_name(),
            task=result._task,
            res=result._result,
        )
        with self.capture_event_data('runner_item_on_ok', **event_data):
            super(CallbackModule, self).v2_runner_item_on_ok(result)

    def v2_runner_item_on_failed(self, result):
        event_data = dict(
            host=result._host.get_name(),
            task=result._task,
            res=result._result,
        )
        with self.capture_event_data('runner_item_on_failed', **event_data):
            super(CallbackModule, self).v2_runner_item_on_failed(result)

    def v2_runner_item_on_skipped(self, result):
        event_data = dict(
            host=result._host.get_name(),
            task=result._task,
            res=result._result,
        )
        with self.capture_event_data('runner_item_on_skipped', **event_data):
            super(CallbackModule, self).v2_runner_item_on_skipped(result)

    def v2_runner_retry(self, result):
        event_data = dict(
            host=result._host.get_name(),
            task=result._task,
            res=result._result,
        )
        with self.capture_event_data('runner_retry', **event_data):
            super(CallbackModule, self).v2_runner_retry(result)

    def v2_runner_on_start(self, host, task):
        event_data = dict(
            host=host.get_name(),
            task=task
        )
        self._host_start[host.get_name()] = current_time()
        with self.capture_event_data('runner_on_start', **event_data):
            super(CallbackModule, self).v2_runner_on_start(host, task)
