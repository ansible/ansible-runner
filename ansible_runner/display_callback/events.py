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

# Python
import base64
import contextlib
import datetime
import json
import multiprocessing
import os
import stat
import threading
import uuid

__all__ = ['event_context']


# use a custom JSON serializer so we can properly handle !unsafe and !vault
# objects that may exist in events emitted by the callback plugin
# see: https://github.com/ansible/ansible/pull/38759
class AnsibleJSONEncoderLocal(json.JSONEncoder):
    '''
    The class AnsibleJSONEncoder exists in Ansible core for this function
    this performs a mostly identical function via duck typing
    '''

    def default(self, o):
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
