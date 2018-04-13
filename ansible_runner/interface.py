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

from .runner_config import RunnerConfig
from .runner import Runner


def run(**kwargs):
    '''
    Run an Ansible Runner task in the foreground and return a Runner object when complete.

    Args:

        private_data_dir (string, path): The directory containing all runner metadata needed
            to invoke the runner module

        ident (string, optional): The run identifier for this invocation of Runner. Will be used
            to create and name the artifact directory holding the results of the invocation

        playbook (string, filename): The playbook relative path located in the private_data_dir/project
            directory that will be invoked by runner when executing Ansible

        inventory (string): Override the inventory directory/file supplied with runner metadata at
            private_data_dir/inventory with a specific list of hosts

        limit (string): Matches ansible's --limit parameter to further constrain the inventory to be used

    Returns:
        Runner: An object that holds details and results from the invocation of Ansible itself
    '''
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

        playbook (string, filename): The playbook relative path located in the private_data_dir/project
            directory that will be invoked by runner when executing Ansible

        inventory (string): Override the inventory directory/file supplied with runner metadata at
            private_data_dir/inventory with a specific list of hosts

        limit (string): Matches ansible's --limit parameter to further constrain the inventory to be used

    Returns:
        threadObj, Runner: An object representing the thread itself and a Runner instance that holds details
        and results from the invocation of Ansible itself
    '''
    rc = RunnerConfig(**kwargs)
    rc.prepare()
    r = Runner(rc)
    runner_thread = threading.Thread(target=r.run)
    runner_thread.start()
    return runner_thread, r


def api(playbook, inventory, limit=None, ident=None):
    '''
    Run an Ansible Runner task in the foreground and return a Runner object
    when complete.

    This function will accept the playbook and inventory as native Python
    objects and write them to temp disk.

    Args:
        playbook (list): The Ansible playbook as a list of dict objects

        inventory (string): The Ansible inventory in INI-style format

        ident (string, optional): The run identifier for this invocation of
            Runner. Will be used to create and name the artifact directory
            holding the results of the invocation

        limit (string): Matches ansible's --limit parameter to further
            constrain the inventory to be used

    Returns:
        Runner: An object that holds details and results from the invocation of
            Ansible itself
    '''
    try:
        private_data_dir = tempfile.mkdtemp()
        kwargs = {'private_data_dir': private_data_dir, 'limit': limit,
                  'ident': ident}

        inputdir = (('playbook', playbook, 'project'),
                    ('inventory', inventory, 'inventory'))

        for name, obj, fldr in inputdir:
            path = os.path.join(private_data_dir, fldr)
            os.makedirs(path)
            fd, fn = tempfile.mkstemp(dir=path)
            kwargs[name] = fn
            with open(fn, 'w') as f:
                if name == 'playbook':
                    f.write(json.dumps(obj))
                else:
                    f.write(obj)

        return run(**kwargs)

    finally:
        shutil.rmtree(private_data_dir)


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
