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
    rc = RunnerConfig(**kwargs)
    rc.prepare()
    r = Runner(rc)
    r.run()
    return r


def run_async(**kwargs):
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
