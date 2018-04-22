from uuid import uuid4
import pkg_resources
import threading
import argparse
import signal
import errno
import json
import stat
import sys
import os
import io
import fcntl
import tempfile

from ConfigParser import ConfigParser, MissingSectionHeaderError
from collections import Iterable

from six import string_types

from .runner_config import RunnerConfig
from .runner import Runner


def isplaybook(obj):
    '''
    Inspects the object and returns if it is a playbook

    Args:
        obj (object): The object to be inspected by this function

    Returns:
        boolean: True if the object is a list and False if it is not
    '''
    return isinstance(obj, Iterable) and not isinstance(obj, string_types)


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
    os.makedirs(path)

    lock_fp = os.path.join(path, '.artifact_lock')
    lock_fd = os.open(lock_fp, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.lockf(lock_fd, fcntl.LOCK_EX)

    try:
        if filename is None:
            fd, fn = tempfile.mkstemp(dir=path)
        else:
            fn = os.path.join(path, filename)

        with open(fn, 'w') as f:
            f.write(str(obj))

    finally:
        fcntl.lockf(lock_fd, fcntl.LOCK_UN)

    return fn


def to_artifacts(kwargs):
    '''
    Introspect the kwargs and dump objects to disk
    '''
    try:
        private_data_dir = kwargs.get('private_data_dir')
        if not private_data_dir:
            private_data_dir = tempfile.mkdtemp()
            kwargs['private_data_dir'] = private_data_dir

        for key in ('playbook', 'inventory'):
            obj = kwargs.get(key)
            if obj:
                if key == 'playbook' and isplaybook(obj):
                    path = os.path.join(private_data_dir, 'project')
                    kwargs['playbook'] = dump_artifact(json.dumps(obj), path)

                elif key == 'inventory' and not os.path.exists(obj):
                    path = os.path.join(private_data_dir, 'inventory')
                    kwargs['inventory'] = dump_artifact(obj, path)

        for key in ('envvars', 'extravars', 'passwords', 'settings'):
            obj = kwargs.get(key)
            if obj:
                path = os.path.join(private_data_dir, 'env')
                dump_artifact(json.dumps(obj), path, filename=key)
                kwargs.pop(key)

        if 'ssh_key' in kwargs:
            path = os.path.join(private_data_dir, 'ssh_key')
            dump_artifact(str(obj), path, filename='ssh_key')
            kwargs.pop('ssh_key')

    except KeyError as exc:
        raise ValueError('missing required keyword argument: %s' % exc)


def run(**kwargs):
    '''
    Run an Ansible Runner task in the foreground and return a Runner object when complete.

    Args:

        private_data_dir (string, path): The directory containing all runner metadata needed
            to invoke the runner module

        ident (string, optional): The run identifier for this invocation of Runner. Will be used
            to create and name the artifact directory holding the results of the invocation

        playbook (string, filename or list): The playbook relative path located in the private_data_dir/project
            directory that will be invoked by runner when executing Ansible.  If this value is provided as a
            Python list object, the playbook will be written to disk and then executed.

        inventory (string): Override the inventory directory/file supplied with runner metadata at
            private_data_dir/inventory with a specific list of hosts.  If this value is provided as
            a INI formatted string, then it will be written to disk and used.

        envvars (dict, optional): Any environment variables to be used when running Ansible.

        extravars (dict, optional): Any extra variables to be passed to Ansible at runtime using
            the -e option when calling ansible-playbook

        passwords (dict, optional): A dict object that contains password prompt patterns and response
            values used when processing output from ansible-playbook

        settings (dict, optional): A dict objec that contains values for ansible-runner runtime
            settings.

        ssh_key (string, optional): The ssh private key passed to ssh-agent as part of the
            ansible-playbook run

        limit (string, optional): Matches ansible's --limit parameter to further constrain the inventory to be used

    Returns:
        Runner: An object that holds details and results from the invocation of Ansible itself
    '''
    to_artifacts(kwargs)
    rc = RunnerConfig(**kwargs)
    rc.prepare()
    r = Runner(rc)
    r.run()
    return r


def run_async(**kwargs):
    '''
    Run an Ansible Runner task in the background and return a thread object and  Runner object when complete.

    Args:

        private_data_dir (string, path): The directory containing all runner metadata needed
            to invoke the runner module

        ident (string, optional): The run identifier for this invocation of Runner. Will be used
            to create and name the artifact directory holding the results of the invocation

        playbook (string, filename or list): The playbook relative path located in the private_data_dir/project
            directory that will be invoked by runner when executing Ansible.  If this value is provided as a
            Python list object, the playbook will be written to disk and then executed.

        inventory (string): Override the inventory directory/file supplied with runner metadata at
            private_data_dir/inventory with a specific list of hosts.  If this value is provided as
            a INI formatted string, then it will be written to disk and used.

        envvars (dict, optional): Any environment variables to be used when running Ansible.

        extravars (dict, optional): Any extra variables to be passed to Ansible at runtime using
            the -e option when calling ansible-playbook

        passwords (dict, optional): A dict object that contains password prompt patterns and response
            values used when processing output from ansible-playbook

        settings (dict, optional): A dict objec that contains values for ansible-runner runtime
            settings.

        ssh_key (string, optional): The ssh private key passed to ssh-agent as part of the
            ansible-playbook run

        limit (string, optional): Matches ansible's --limit parameter to further constrain the inventory to be used

    Returns:
        threadObj, Runner: An object representing the thread itself and a Runner instance that holds details
        and results from the invocation of Ansible itself
    '''
    to_artifacts(kwargs)
    rc = RunnerConfig(**kwargs)
    rc.prepare()
    r = Runner(rc)
    runner_thread = threading.Thread(target=r.run)
    runner_thread.start()
    return runner_thread, r



def main():
    version = pkg_resources.require("ansible_runner")[0].version
    parser = argparse.ArgumentParser(description='manage ansible execution')
    parser.add_argument('--version', action='version', version=version)
    parser.add_argument('command', choices=['run', 'start',
                                            'stop', 'is-alive'])
    parser.add_argument('private_data_dir',
                        help='Base directory containing Runner metadata (project, inventory, etc')
    parser.add_argument("--hosts")
    parser.add_argument("-p", "--playbook", default=os.getenv("RUNNER_PLAYBOOK", None))
    parser.add_argument("-i", "--ident",
                        default=uuid4(),
                        help="An identifier that will be used when generating the"
                             "artifacts directory and can be used to uniquely identify a playbook run")
    args = parser.parse_args()
    pidfile = os.path.join(args.private_data_dir, 'pid')
    try:
        os.makedirs(args.private_data_dir)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(args.private_data_dir):
            pass
        else:
            raise
    stderr_path = os.path.join(args.private_data_dir, 'daemon.log')
    if not os.path.exists(stderr_path):
        os.mknod(stderr_path, stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR)
    stderr = open(stderr_path, 'w+')

    if args.command in ('start', 'run'):
        if args.command == 'start':
            import daemon
            from daemon.pidfile import TimeoutPIDLockFile
            context = daemon.DaemonContext(
                pidfile=TimeoutPIDLockFile(pidfile),
                stderr=stderr
            )
        else:
            context = threading.Lock()
        with context:
            run_options = dict(private_data_dir=args.private_data_dir,
                               ident=args.ident,
                               playbook=args.playbook)
            if args.hosts is not None:
                run_options.update(inventory=args.hosts)
            run(**run_options)

    try:
        with open(pidfile, 'r') as f:
            pid = int(f.readline())
    except IOError:
        sys.exit(1)

    if args.command == 'stop':
        try:
            with open(os.path.join(args.private_data_dir, 'args'), 'r') as args:
                Runner.handle_termination(pid, json.load(args), 'bwrap')
        except IOError:
            Runner.handle_termination(pid, [], 'bwrap')
    elif args.command == 'is-alive':
        try:
            os.kill(pid, signal.SIG_DFL)
            sys.exit(0)
        except OSError:
            sys.exit(1)
