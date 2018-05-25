import base64
import json
import sys
import re
import os
import fcntl
import tempfile
import hashlib
import logging

from functools import partial
from collections import Iterable, Mapping
from io import StringIO
from six import string_types


STDOUT_MSG_FORMAT = '%(message)s'
DEBUG_MSG_FORMAT = '%(asctime)s:[%(module)s.%(funcName)s:%(lineno)s]: %(message)s'

LOGGER = logging.getLogger('ansible-runner')


display = partial(LOGGER.log, 60)


def configure_logging(filename=None, debug=False):
    '''
    Configures the logging facility

    Args:
        filename (string): The name of the file to log debug messages to.  If
            this argument is None, then file logging is disabled.

        debug (string): Specifies if debug should be sent to stdout.  If the
            value of this argument is True, debug messages are sent to
            stdout.  If this value is False, only display messages (level 60)
            are sent ot stdout.

    Returns:
        None
    '''
    root_logger = logging.getLogger('')
    root_logger.setLevel(logging.DEBUG)

    # Set up logging to a file
    if filename:
        file_handler = logging.FileHandler(filename)
        formatter = logging.Formatter(DEBUG_MSG_FORMAT)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    stdout_handler = logging.StreamHandler(sys.stdout)

    if debug:
        stdout_handler.setLevel(10)
        formatter = logging.Formatter(DEBUG_MSG_FORMAT)
    else:
        stdout_handler.setLevel(60)
        formatter = logging.Formatter(STDOUT_MSG_FORMAT)

    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)


def isplaybook(obj):
    '''
    Inspects the object and returns if it is a playbook

    Args:
        obj (object): The object to be inspected by this function

    Returns:
        boolean: True if the object is a list and False if it is not
    '''
    return isinstance(obj, Iterable) and (not isinstance(obj, string_types) and not isinstance(obj, Mapping))


def isinventory(obj):
    '''
    Inspects the object and returns if it is an inventory

    Args:
        obj (object): The object to be inspected by this function

    Returns:
        boolean: True if the object is an inventory dict and False if it is not
    '''
    return isinstance(obj, Mapping) or isinstance(obj, string_types)


def dump_artifact(obj, path, filename=None):
    '''
    Write the artifact to disk at the specified path

    Args:
        obj (string): The string object to be dumped to disk in the specified
            path.  The artifact filename will be automatically created

        path (string): The full path to the artifacts data directory.

        filename (string, optional): The name of file to write the artifact to.
            If the filename is not provided, then one will be generated.

    Returns:
        string: The full path filename for the artifact that was generated
    '''
    p_sha1 = None

    if not os.path.exists(path):
        os.makedirs(path)
    else:
        p_sha1 = hashlib.sha1()
        p_sha1.update(obj)

    if filename is None:
        fd, fn = tempfile.mkstemp(dir=path)
    else:
        fn = os.path.join(path, filename)

    if os.path.exists(fn):
        c_sha1 = hashlib.sha1()
        c_sha1.update(open(fn).read())

    if not os.path.exists(fn) or p_sha1.hexdigest() != c_sha1.hexdigest():
        lock_fp = os.path.join(path, '.artifact_write_lock')
        lock_fd = os.open(lock_fp, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.lockf(lock_fd, fcntl.LOCK_EX)

        try:
            with open(fn, 'w') as f:
                f.write(str(obj))
        finally:
            fcntl.lockf(lock_fd, fcntl.LOCK_UN)
            os.remove(lock_fp)

    return fn


def dump_artifacts(kwargs):
    '''
    Introspect the kwargs and dump objects to disk
    '''
    private_data_dir = kwargs.get('private_data_dir')
    if not private_data_dir:
        private_data_dir = tempfile.mkdtemp()
        kwargs['private_data_dir'] = private_data_dir

    if not os.path.exists(private_data_dir):
        raise ValueError('private_data_dir path is either invalid or does not exist')

    for key in ('playbook', 'inventory'):
        obj = kwargs.get(key)
        if obj:
            if key == 'playbook' and isplaybook(obj):
                path = os.path.join(private_data_dir, 'project')
                kwargs['playbook'] = dump_artifact(json.dumps(obj), path, 'main.json')

            elif key == 'inventory' and isinventory(obj):
                path = os.path.join(private_data_dir, 'inventory')
                if isinstance(obj, Mapping):
                    kwargs['inventory'] = dump_artifact(json.dumps(obj), path, 'hosts.json')
                elif isinstance(obj, string_types):
                    if not os.path.exists(obj):
                        kwargs['inventory'] = dump_artifact(obj, path, 'hosts')

    for key in ('envvars', 'extravars', 'passwords', 'settings'):
        obj = kwargs.get(key)
        if obj:
            path = os.path.join(private_data_dir, 'env')
            dump_artifact(json.dumps(obj), path, key)
            kwargs.pop(key)

    if 'ssh_key' in kwargs:
        path = os.path.join(private_data_dir, 'env')
        dump_artifact(str(kwargs['ssh_key']), path, 'ssh_key')
        kwargs.pop('ssh_key')


class OutputEventFilter(object):
    '''
    File-like object that looks for encoded job events in stdout data.
    '''

    EVENT_DATA_RE = re.compile(r'\x1b\[K((?:[A-Za-z0-9+/=]+\x1b\[\d+D)+)\x1b\[K')

    def __init__(self, handle, event_callback):
        self._event_callback = event_callback
        self._event_ct = 0
        self._counter = 1
        self._start_line = 0
        self._handle = handle
        self._buffer = StringIO()
        self._last_chunk = ''
        self._current_event_data = None

    def flush(self):
        # pexpect wants to flush the file it writes to, but we're not
        # actually capturing stdout to a raw file; we're just
        # implementing a custom `write` method to discover and emit events from
        # the stdout stream
        pass

    def write(self, data):
        self._buffer.write(data)

        # keep a sliding window of the last chunk written so we can detect
        # event tokens and determine if we need to perform a search of the full
        # buffer
        should_search = '\x1b[K' in (self._last_chunk + data)
        self._last_chunk = data

        # Only bother searching the buffer if we recently saw a start/end
        # token (\x1b[K)
        while should_search:
            value = self._buffer.getvalue()
            match = self.EVENT_DATA_RE.search(value)
            if not match:
                break
            try:
                base64_data = re.sub(r'\x1b\[\d+D', '', match.group(1))
                event_data = json.loads(base64.b64decode(base64_data))
            except ValueError:
                event_data = {}
            event_data = self._emit_event(value[:match.start()], event_data)
            stdout_actual = event_data['stdout'] if 'stdout' in event_data else None
            remainder = value[match.end():]
            self._buffer = StringIO()
            self._buffer.write(remainder)

            if stdout_actual:
                sys.stdout.write(stdout_actual + "\n")
                self._handle.write(stdout_actual + "\n")

            self._last_chunk = remainder
        else:
            sys.stdout.write(data + '\n')
            self._handle.write(data + '\n')

    def close(self):
        value = self._buffer.getvalue()
        if value:
            self._emit_event(value)
            self._buffer = StringIO()
        self._event_callback(dict(event='EOF'))

    def _emit_event(self, buffered_stdout, next_event_data=None):
        next_event_data = next_event_data or {}
        if self._current_event_data:
            event_data = self._current_event_data
            stdout_chunks = [buffered_stdout]
        elif buffered_stdout:
            event_data = dict(event='verbose')
            stdout_chunks = buffered_stdout.splitlines(True)
        else:
            event_data = dict()
            stdout_chunks = []

        for stdout_chunk in stdout_chunks:
            event_data['counter'] = self._counter
            self._counter += 1
            event_data['stdout'] = stdout_chunk[:-2] if len(stdout_chunk) > 2 else ""
            n_lines = stdout_chunk.count('\n')
            event_data['start_line'] = self._start_line
            event_data['end_line'] = self._start_line + n_lines
            self._start_line += n_lines
            if self._event_callback:
                self._event_callback(event_data)
                self._event_ct += 1
        if next_event_data.get('uuid', None):
            self._current_event_data = next_event_data
        else:
            self._current_event_data = None
        return event_data
