
import json
import sys
import re
import os
import stat
import fcntl
import shutil
import hashlib
import tempfile
import subprocess
import base64
import threading
import pipes
import uuid
import codecs

from distutils.spawn import find_executable
from ansible_runner.exceptions import ConfigurationError

try:
    from collections.abc import Iterable, Mapping
except ImportError:
    from collections import Iterable, Mapping
from io import StringIO
from six import string_types, PY2, PY3, text_type, binary_type


class Bunch(object):

    '''
    Collect a bunch of variables together in an object.
    This is a slight modification of Alex Martelli's and Doug Hudgeon's Bunch pattern.
    '''

    def __init__(self, **kwargs):
        self.update(**kwargs)

    def update(self, **kwargs):
        self.__dict__.update(kwargs)

    def get(self, key):
        return self.__dict__.get(key)


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


def check_isolation_executable_installed(isolation_executable):
    '''
    Check that process isolation executable (e.g. podman, docker, bwrap) is installed.
    '''
    cmd = [isolation_executable, '--version']
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        proc.communicate()
        return bool(proc.returncode == 0)
    except (OSError, ValueError) as e:
        if isinstance(e, ValueError) or getattr(e, 'errno', 1) != 2:  # ENOENT, no such file or directory
            raise RuntimeError(f'{isolation_executable} unavailable for unexpected reason.')
        return False


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
        os.makedirs(path, mode=0o700)
    else:
        p_sha1 = hashlib.sha1()
        p_sha1.update(obj.encode(encoding='UTF-8'))

    if filename is None:
        fd, fn = tempfile.mkstemp(dir=path)
    else:
        fn = os.path.join(path, filename)

    if os.path.exists(fn):
        c_sha1 = hashlib.sha1()
        with open(fn) as f:
            contents = f.read()
        c_sha1.update(contents.encode(encoding='UTF-8'))

    if not os.path.exists(fn) or p_sha1.hexdigest() != c_sha1.hexdigest():
        lock_fp = os.path.join(path, '.artifact_write_lock')
        lock_fd = os.open(lock_fp, os.O_RDWR | os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR)
        fcntl.lockf(lock_fd, fcntl.LOCK_EX)

        try:
            with open(fn, 'w') as f:
                os.chmod(fn, stat.S_IRUSR)
                f.write(str(obj))
        finally:
            fcntl.lockf(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            os.remove(lock_fp)

    return fn


def cleanup_artifact_dir(path, num_keep=0):
    # 0 disables artifact dir cleanup/rotation
    if num_keep < 1:
        return
    all_paths = sorted([os.path.join(path, p) for p in os.listdir(path)],
                       key=lambda x: os.path.getmtime(x))
    total_remove = len(all_paths) - num_keep
    for f in range(total_remove):
        shutil.rmtree(all_paths[f])


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

    if 'role' in kwargs:
        role = {'name': kwargs.pop('role')}
        if 'role_vars' in kwargs:
            role['vars'] = kwargs.pop('role_vars')

        play = [{'hosts': kwargs.pop('hosts', 'all'), 'roles': [role]}]

        if kwargs.pop('role_skip_facts', False):
            play[0]['gather_facts'] = False

        kwargs['playbook'] = play

        if 'envvars' not in kwargs:
            kwargs['envvars'] = {}

        roles_path = kwargs.pop('roles_path', None)
        if not roles_path:
            roles_path = os.path.join(private_data_dir, 'roles')
        else:
            roles_path += ':{}'.format(os.path.join(private_data_dir, 'roles'))

        kwargs['envvars']['ANSIBLE_ROLES_PATH'] = roles_path

    obj = kwargs.get('playbook')
    if obj and isplaybook(obj):
        path = os.path.join(private_data_dir, 'project')
        kwargs['playbook'] = dump_artifact(json.dumps(obj), path, 'main.json')

    obj = kwargs.get('inventory')
    if obj and isinventory(obj):
        path = os.path.join(private_data_dir, 'inventory')
        if isinstance(obj, Mapping):
            kwargs['inventory'] = dump_artifact(json.dumps(obj), path, 'hosts.json')
        elif isinstance(obj, string_types):
            if not os.path.exists(obj):
                kwargs['inventory'] = dump_artifact(obj, path, 'hosts')

    for key in ('envvars', 'extravars', 'passwords', 'settings'):
        obj = kwargs.get(key)
        if obj and not os.path.exists(os.path.join(private_data_dir, 'env', key)):
            path = os.path.join(private_data_dir, 'env')
            dump_artifact(json.dumps(obj), path, key)
            kwargs.pop(key)

    for key in ('ssh_key', 'cmdline'):
        obj = kwargs.get(key)
        if obj and not os.path.exists(os.path.join(private_data_dir, 'env', key)):
            path = os.path.join(private_data_dir, 'env')
            dump_artifact(str(kwargs[key]), path, key)
            kwargs.pop(key)


def collect_new_events(event_path,old_events):
    '''
    Collect new events for the 'events' generator property
    '''
    dir_events = os.listdir(event_path)
    dir_events_actual = []
    for each_file in dir_events:
        if re.match("^[0-9]+-.+json$", each_file):
            if '-partial' not in each_file and each_file not in old_events.keys() :
                dir_events_actual.append(each_file)
    dir_events_actual.sort(key=lambda filenm: int(filenm.split("-", 1)[0]))
    for event_file in dir_events_actual:
        with codecs.open(os.path.join(event_path, event_file), 'r', encoding='utf-8') as event_file_actual:
            try:
                event = json.load(event_file_actual)
            except ValueError:
                break

        old_events[event_file] = True
        yield event, old_events


class OutputEventFilter(object):
    '''
    File-like object that looks for encoded job events in stdout data.
    '''

    EVENT_DATA_RE = re.compile(r'\x1b\[K((?:[A-Za-z0-9+/=]+\x1b\[\d+D)+)\x1b\[K')

    def __init__(self, handle, event_callback,
                 suppress_ansible_output=False, output_json=False):
        self._event_callback = event_callback
        self._counter = 0
        self._start_line = 0
        self._handle = handle
        self._buffer = StringIO()
        self._last_chunk = ''
        self._current_event_data = None
        self.output_json = output_json
        self.suppress_ansible_output = suppress_ansible_output

    def flush(self):
        self._handle.flush()

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
                event_data = json.loads(base64.b64decode(base64_data).decode('utf-8'))
            except ValueError:
                event_data = {}
            event_data = self._emit_event(value[:match.start()], event_data)
            if not self.output_json:
                stdout_actual = event_data['stdout'] if 'stdout' in event_data else None
            else:
                stdout_actual = json.dumps(event_data)
            remainder = value[match.end():]
            self._buffer = StringIO()
            self._buffer.write(remainder)

            if stdout_actual and stdout_actual != "{}":
                if not self.suppress_ansible_output:
                    sys.stdout.write(
                        stdout_actual.encode('utf-8') if PY2 else stdout_actual
                    )
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                self._handle.write(stdout_actual + "\n")
                self._handle.flush()

            self._last_chunk = remainder
        else:
            # Verbose stdout outside of event data context
            if data and '\n' in data and self._current_event_data is None:
                # emit events for all complete lines we know about
                lines = self._buffer.getvalue().splitlines(True)  # keep ends
                remainder = None
                # if last line is not a complete line, then exclude it
                if '\n' not in lines[-1]:
                    remainder = lines.pop()
                # emit all complete lines
                for line in lines:
                    self._emit_event(line)
                    if not self.suppress_ansible_output:
                        sys.stdout.write(
                            line.encode('utf-8') if PY2 else line
                        )
                    self._handle.write(line)
                    self._handle.flush()
                self._buffer = StringIO()
                # put final partial line back on buffer
                if remainder:
                    self._buffer.write(remainder)

    def close(self):
        value = self._buffer.getvalue()
        if value:
            self._emit_event(value)
            self._buffer = StringIO()
        self._event_callback(dict(event='EOF'))
        self._handle.close()

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
            if event_data.get('event') == 'verbose':
                event_data['uuid'] = str(uuid.uuid4())
            self._counter += 1
            event_data['counter'] = self._counter
            event_data['stdout'] = stdout_chunk[:-2] if len(stdout_chunk) > 2 else ""
            n_lines = stdout_chunk.count('\n')
            event_data['start_line'] = self._start_line
            event_data['end_line'] = self._start_line + n_lines
            self._start_line += n_lines
            if self._event_callback:
                self._event_callback(event_data)
        if next_event_data.get('uuid', None):
            self._current_event_data = next_event_data
        else:
            self._current_event_data = None
        return event_data


def open_fifo_write(path, data):
    '''open_fifo_write opens the fifo named pipe in a new thread.
    This blocks the thread until an external process (such as ssh-agent)
    reads data from the pipe.
    '''
    os.mkfifo(path, stat.S_IRUSR | stat.S_IWUSR)
    threading.Thread(target=lambda p, d: open(p, 'wb').write(d),
                     args=(path, data)).start()


def args2cmdline(*args):
    return ' '.join([pipes.quote(a) for a in args])


def ensure_str(s, encoding='utf-8', errors='strict'):
    """
    Copied from six==1.12

    Coerce *s* to `str`.
    For Python 2:
      - `unicode` -> encoded to `str`
      - `str` -> `str`
    For Python 3:
      - `str` -> `str`
      - `bytes` -> decoded to `str`
    """
    if not isinstance(s, (text_type, binary_type)):
        raise TypeError("not expecting type '%s'" % type(s))
    if PY2 and isinstance(s, text_type):
        s = s.encode(encoding, errors)
    elif PY3 and isinstance(s, binary_type):
        s = s.decode(encoding, errors)
    return s


def sanitize_container_name(original_name):
    """
    Docker and podman will only accept certain characters in container names
    This takes a given name from user-specified values and replaces the
    invalid characters so it can be used in docker/podman CLI commands
    """
    return re.sub('[^a-zA-Z0-9_-]', '_', text_type(original_name))


def cli_mounts():
    return [
        {
            'ENVS': ['SSH_AUTH_SOCK'],
            'PATHS': [
                {
                    'src': '{}/.ssh/'.format(os.environ['HOME']),
                    'dest': '/home/runner/.ssh/'
                },
                {
                    'src': '/etc/ssh/ssh_known_hosts',
                    'dest': '/etc/ssh/ssh_known_hosts'
                }
            ]
        },
    ]


def santize_json_response(data):
    '''
    Removes warning message from response message emitted by ansible
    command line utilities.
    :param action: The string data to be santizied
    :type action: str
    '''
    start_re = re.compile("{(.|\n)*", re.MULTILINE)
    data = start_re.search(data).group().strip()
    return data


def get_executable_path(name):
    exec_path = find_executable(name)
    if exec_path is None:
        raise ConfigurationError(f"{name} command not found")
    return exec_path
