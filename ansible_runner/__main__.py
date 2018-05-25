#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
import pkg_resources
import threading
import argparse
import signal
import errno
import json
import stat
import sys
import os
import shlex

from uuid import uuid4

from yaml import safe_load

from ansible_runner import run
from ansible_runner.utils import dump_artifact
from ansible_runner.runner import Runner

VERSION = pkg_resources.require("ansible_runner")[0].version

DEFAULT_ROLES_PATH = os.getenv('ANSIBLE_ROLES_PATH', None)
DEFAULT_RUNNER_PLAYBOOK = os.getenv('RUNNER_PLAYBOOK', None)
DEFAULT_RUNNER_ROLE = os.getenv('RUNNER_ROLE', None)


def main():
    parser = argparse.ArgumentParser(description='manage ansible execution')

    parser.add_argument('--version', action='version', version=VERSION)

    parser.add_argument('command', choices=['run', 'start', 'stop', 'is-alive'])

    parser.add_argument('private_data_dir',
                        help='Base directory containing Runner metadata (project, inventory, etc')

    group = parser.add_mutually_exclusive_group()

    group.add_argument("-p", "--playbook", default=DEFAULT_RUNNER_PLAYBOOK,
                       help="The name of the playbook to execute")

    group.add_argument("-r", "--role", default=DEFAULT_RUNNER_ROLE,
                       help="Invoke an Ansible role directly without a playbook")

    parser.add_argument("--hosts", default='all',
                        help="Define the set of hosts to execute against")

    parser.add_argument("-i", "--ident",
                        default=uuid4(),
                        help="An identifier that will be used when generating the"
                             "artifacts directory and can be used to uniquely identify a playbook run")

    parser.add_argument("--roles-path", default=DEFAULT_ROLES_PATH,
                        help="Path to the Ansible roles directory")

    parser.add_argument("--role-vars",
                        help="Variables to pass to the role at runtime")

    parser.add_argument("--inventory")

    args = parser.parse_args()

    pidfile = os.path.join(args.private_data_dir, 'pid')

    try:
        os.makedirs(args.private_data_dir)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(args.private_data_dir):
            pass
        else:
            raise

    if args.command != 'run':
        stderr_path = os.path.join(args.private_data_dir, 'daemon.log')
        if not os.path.exists(stderr_path):
            os.mknod(stderr_path, stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR)
        stderr = open(stderr_path, 'w+')

    if args.command in ('start', 'run'):
        if args.role:

            role = {'name': args.role}
            if args.role_vars:
                role_vars = {}
                for item in shlex.split(args.role_vars):
                    key, value = item.split('=')
                    role_vars[key] = value
                role['vars'] = role_vars

            kwargs = {'private_data_dir': args.private_data_dir}

            playbook = None
            tmpvars = None

            rc = 255

            try:
                play = [{'hosts': args.hosts, 'roles': [role]}]

                path = os.path.abspath(os.path.join(args.private_data_dir, 'project'))
                filename = str(uuid4().hex)

                playbook = dump_artifact(json.dumps(play), path, filename)
                kwargs['playbook'] = playbook
                print('using playbook file %s' % playbook)

                if args.inventory:
                    inventory_file = os.path.abspath(os.path.join(args.private_data_dir, 'inventory', args.inventory))
                    kwargs['inventory'] = inventory_file
                    print('using inventory file %s' % inventory_file)

                envvars = {}

                roles_path = args.roles_path or os.path.join(args.private_data_dir, 'roles')
                roles_path = os.path.abspath(roles_path)
                print('setting ANSIBLE_ROLES_PATH to %s' % roles_path)

                # since envvars will overwrite an existing envvars, capture
                # the content of the current envvars if it exists and
                # restore it once done
                envvars = {}
                curvars = os.path.join(args.private_data_dir, 'env/envvars')
                if os.path.exists(curvars):
                    with open(curvars, 'rb') as f:
                        tmpvars = f.read()
                        envvars = safe_load(tmpvars)
                envvars['ANSIBLE_ROLES_PATH'] = roles_path
                kwargs['envvars'] = envvars

                res = run(**kwargs)
                rc = res.rc

            finally:
                if playbook and os.path.isfile(playbook):
                    os.remove(playbook)

                # if a previous envvars existed in the private_data_dir,
                # restore the original file contents
                if tmpvars:
                    with open(curvars, 'wb') as f:
                        f.write(tmpvars)

            sys.exit(rc)

        elif args.command == 'start':
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
            sys.exit(0)

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
