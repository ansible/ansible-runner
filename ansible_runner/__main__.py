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
import logging
import signal
import errno
import json
import stat
import sys
import os
import shlex
import shutil

from uuid import uuid4

from yaml import safe_load

from ansible_runner import run
from ansible_runner import output
from ansible_runner.utils import dump_artifact
from ansible_runner.runner import Runner
from ansible_runner.exceptions import AnsibleRunnerException

VERSION = pkg_resources.require("ansible_runner")[0].version

DEFAULT_ROLES_PATH = os.getenv('ANSIBLE_ROLES_PATH', None)
DEFAULT_RUNNER_PLAYBOOK = os.getenv('RUNNER_PLAYBOOK', None)
DEFAULT_RUNNER_ROLE = os.getenv('RUNNER_ROLE', None)

logger = logging.getLogger('ansible-runner')


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

    parser.add_argument("--hosts",
                        help="Define the set of hosts to execute against")

    parser.add_argument("-i", "--ident",
                        default=uuid4(),
                        help="An identifier that will be used when generating the"
                             "artifacts directory and can be used to uniquely identify a playbook run")

    parser.add_argument("--roles-path", default=DEFAULT_ROLES_PATH,
                        help="Path to the Ansible roles directory")

    parser.add_argument("--role-vars",
                        help="Variables to pass to the role at runtime")

    parser.add_argument("--role-skip-facts", action="store_true", default=False,
                        help="Disable fact collection when executing a role directly")
    parser.add_argument("--artifact-dir",
                        help="Optional Path for the artifact root directory, by default it is located inside the private data dir")

    parser.add_argument("--inventory",
                        help="Override the default inventory location in private_data_dir")

    parser.add_argument("-j", "--json", action="store_true",
                        help="Output the json event structure to stdout instead of Ansible output")

    parser.add_argument("-v", action="count",
                        help="Increase the verbosity with multiple v's (up to 5) of the ansible-playbook output")

    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Disable all output")

    parser.add_argument("--cmdline",
                        help="Command line options to pass to ansible-playbook at execution time")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug output logging")

    parser.add_argument("--logfile",
                        help="Log output messages to a file")

    args = parser.parse_args()

    output.configure()

    # enable or disable debug mode
    output.set_debug('enable' if args.debug else 'disable')

    # set the output logfile
    if args.logfile:
        output.set_logfile(args.logfile)

    output.debug('starting debug logging')

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
            os.close(os.open(stderr_path, os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR))
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

            kwargs = dict(private_data_dir=args.private_data_dir,
                          json_mode=args.json)
            if args.artifact_dir:
                kwargs['artifact_dir'] = args.artifact_dir

            project_path = os.path.abspath(os.path.join(args.private_data_dir, 'project'))
            project_exists = os.path.exists(project_path)

            env_path = os.path.join(args.private_data_dir, 'env')
            env_exists = os.path.exists(env_path)

            envvars_path = os.path.join(args.private_data_dir, 'env/envvars')
            envvars_exists = os.path.exists(envvars_path)

            if args.cmdline:
                kwargs['cmdline'] = args.cmdline

            playbook = None
            tmpvars = None

            rc = 255
            errmsg = None

            try:
                play = [{'hosts': args.hosts if args.hosts is not None else "all",
                         'gather_facts': not args.role_skip_facts,
                         'roles': [role]}]

                filename = str(uuid4().hex)

                playbook = dump_artifact(json.dumps(play), project_path, filename)
                kwargs['playbook'] = playbook
                output.debug('using playbook file %s' % playbook)

                if args.inventory:
                    inventory_file = os.path.abspath(os.path.join(args.private_data_dir, 'inventory', args.inventory))
                    if not os.path.exists(inventory_file):
                        raise AnsibleRunnerException('location specified by --inventory does not exist')
                    kwargs['inventory'] = inventory_file
                    output.debug('using inventory file %s' % inventory_file)

                roles_path = args.roles_path or os.path.join(args.private_data_dir, 'roles')
                roles_path = os.path.abspath(roles_path)
                output.debug('setting ANSIBLE_ROLES_PATH to %s' % roles_path)

                envvars = {}
                if envvars_exists:
                    with open(envvars_path, 'rb') as f:
                        tmpvars = f.read()
                        envvars = safe_load(tmpvars)

                envvars['ANSIBLE_ROLES_PATH'] = roles_path
                kwargs['envvars'] = envvars

                res = run(**kwargs)
                rc = res.rc

            except AnsibleRunnerException as exc:
                errmsg = str(exc)

            finally:
                if not project_exists and os.path.exists(project_path):
                    logger.debug('removing dynamically generated project folder')
                    shutil.rmtree(project_path)
                elif playbook and os.path.isfile(playbook):
                    logger.debug('removing dynamically generated playbook')
                    os.remove(playbook)

                # if a previous envvars existed in the private_data_dir,
                # restore the original file contents
                if tmpvars:
                    with open(envvars_path, 'wb') as f:
                        f.write(tmpvars)
                elif not envvars_exists and os.path.exists(envvars_path):
                    logger.debug('removing dynamically generated envvars folder')
                    os.remove(envvars_path)

                # since ansible-runner created the env folder, remove it
                if not env_exists and os.path.exists(env_path):
                    logger.debug('removing dynamically generated env folder')
                    shutil.rmtree(env_path)

            if errmsg:
                print('ansible-runner: ERROR: %s' % errmsg)

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
                               playbook=args.playbook,
                               verbosity=args.v,
                               quiet=args.quiet,
                               json_mode=args.json)

            if args.hosts is not None:
                run_options.update(inventory=args.hosts)

            if args.cmdline:
                run_options['cmdline'] = args.cmdline

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
