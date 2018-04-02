#! /usr/bin/env python

import argparse
import codecs
import collections
import logging
import json
import yaml
import os
import stat
import pipes
import re
import signal
import sys
import thread
import time
import pkg_resources
from uuid import uuid4

import pexpect
import psutil


logger = logging.getLogger('ansible_runner.run')


def main():
    version = pkg_resources.require("ansible_runner")[0].version
    parser = argparse.ArgumentParser(description='manage ansible execution')
    parser.add_argument('--version', action='version', version=version)
    parser.add_argument('command', choices=['run', 'start',
                                            'stop', 'is-alive'])
    parser.add_argument('private_data_dir')
    parser.add_argument("--hosts")
    parser.add_argument("-p", "--playbook", default=os.getenv("RUNNER_PLAYBOOK", None))
    parser.add_argument("-i", "--ident",
                        default=uuid4(),
                        help="An identifier that will be used when generating the"
                             "artifacts directory and can be used to uniquely identify a playbook run")
    parser.add_argument("--skip-ident",
                        action="store_true",
                        help="Do not generate a playbook run identifier")
    args = parser.parse_args()

    private_data_dir = args.private_data_dir
    if args.skip_ident:
        artifact_dir = os.path.join(private_data_dir, 'artifacts')
    else:
        print("Ident: {}".format(args.ident))
        artifact_dir = os.path.join(private_data_dir, "artifacts", "{}".format(args.ident))
    if not os.path.exists(artifact_dir):
        os.makedirs(artifact_dir)
    pidfile = os.path.join(private_data_dir, 'pid')
    if args.hosts is None:
        hosts_actual = os.getenv("RUNNER_HOSTS", os.path.join(private_data_dir, "inventory"))
    else:
        hosts_actual = args.hosts

    print("Hosts: {}".format(hosts_actual))
    print("Playbook: {}".format(args.playbook))

    if args.command in ('start', 'run'):
        # create a file to log stderr in case the daemonized process throws
        # an exception before it gets to `pexpect.spawn`
        stderr_path = os.path.join(artifact_dir, 'daemon.log')
        if not os.path.exists(stderr_path):
            os.mknod(stderr_path, stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR)
        stderr = open(stderr_path, 'w+')

        if args.command == 'start':
            import daemon
            from daemon.pidfile import TimeoutPIDLockFile
            context = daemon.DaemonContext(
                pidfile=TimeoutPIDLockFile(pidfile),
                stderr=stderr
            )
        else:
            import threading
            context = threading.Lock()
        with context:
            __run__(private_data_dir, hosts=hosts_actual,
                    playbook=args.playbook, artifact_dir=artifact_dir)
        sys.exit(0)

    try:
        with open(pidfile, 'r') as f:
            pid = int(f.readline())
    except IOError:
        sys.exit(1)

    if args.command == 'stop':
        try:
            with open(os.path.join(private_data_dir, 'args'), 'r') as args:
                handle_termination(pid, json.load(args), 'bwrap')
        except IOError:
            handle_termination(pid, [], 'bwrap')
    elif args.command == 'is-alive':
        try:
            os.kill(pid, signal.SIG_DFL)
            sys.exit(0)
        except OSError:
            sys.exit(1)


if __name__ == '__main__':
    main()
