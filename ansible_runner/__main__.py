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
import ast
import pkg_resources
import threading
import traceback
import argparse
import logging
import signal
import sys
import errno
import json
import stat
import os
import shutil
from contextlib import contextmanager

from uuid import uuid4

from yaml import safe_load

from ansible_runner import run
from ansible_runner import output
from ansible_runner.utils import dump_artifact, Bunch
from ansible_runner.runner import Runner
from ansible_runner.exceptions import AnsibleRunnerException

VERSION = pkg_resources.require("ansible_runner")[0].version

DEFAULT_ROLES_PATH = os.getenv('ANSIBLE_ROLES_PATH', None)
DEFAULT_RUNNER_BINARY = os.getenv('RUNNER_BINARY', None)
DEFAULT_RUNNER_PLAYBOOK = os.getenv('RUNNER_PLAYBOOK', None)
DEFAULT_RUNNER_ROLE = os.getenv('RUNNER_ROLE', None)
DEFAULT_RUNNER_MODULE = os.getenv('RUNNER_MODULE', None)

logger = logging.getLogger('ansible-runner')


@contextmanager
def role_manager(args):
    if args.role:
        role = {'name': args.role}
        if args.role_vars:
            role_vars = {}
            for item in args.role_vars.split():
                key, value = item.split('=')
                try:
                    role_vars[key] = ast.literal_eval(value)
                except Exception:
                    role_vars[key] = value
            role['vars'] = role_vars

        kwargs = Bunch(**args.__dict__)
        kwargs.update(private_data_dir=args.private_data_dir,
                      json_mode=args.json,
                      ignore_logging=False,
                      project_dir=args.project_dir,
                      rotate_artifacts=args.rotate_artifacts)
        if args.artifact_dir:
            kwargs.artifact_dir = args.artifact_dir

        if args.project_dir:
            project_path = kwargs.project_dir = args.project_dir
        else:
            project_path = os.path.join(args.private_data_dir, 'project')

        project_exists = os.path.exists(project_path)

        env_path = os.path.join(args.private_data_dir, 'env')
        env_exists = os.path.exists(env_path)

        envvars_path = os.path.join(args.private_data_dir, 'env/envvars')
        envvars_exists = os.path.exists(envvars_path)

        if args.cmdline:
            kwargs.cmdline = args.cmdline

        playbook = None
        tmpvars = None

        play = [{'hosts': args.hosts if args.hosts is not None else "all",
                 'gather_facts': not args.role_skip_facts,
                 'roles': [role]}]

        filename = str(uuid4().hex)

        playbook = dump_artifact(json.dumps(play), project_path, filename)
        kwargs.playbook = playbook
        output.debug('using playbook file %s' % playbook)

        if args.inventory:
            inventory_file = os.path.join(args.private_data_dir, 'inventory', args.inventory)
            if not os.path.exists(inventory_file):
                raise AnsibleRunnerException('location specified by --inventory does not exist')
            kwargs.inventory = inventory_file
            output.debug('using inventory file %s' % inventory_file)

        roles_path = args.roles_path or os.path.join(args.private_data_dir, 'roles')
        roles_path = os.path.abspath(roles_path)
        output.debug('setting ANSIBLE_ROLES_PATH to %s' % roles_path)

        envvars = {}
        if envvars_exists:
            with open(envvars_path, 'rb') as f:
                tmpvars = f.read()
                new_envvars = safe_load(tmpvars)
                if new_envvars:
                    envvars = new_envvars

        envvars['ANSIBLE_ROLES_PATH'] = roles_path
        kwargs.envvars = envvars
    else:
        kwargs = args

    yield kwargs

    if args.role:
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


def main(sys_args=None):
    parser = argparse.ArgumentParser(description='manage ansible execution')

    parser.add_argument('--version', action='version', version=VERSION)

    parser.add_argument('command', choices=['run', 'start', 'stop', 'is-alive'])

    parser.add_argument('private_data_dir',
                        help='Base directory containing Runner metadata (project, inventory, etc')

    group = parser.add_mutually_exclusive_group()

    group.add_argument("-m", "--module", default=DEFAULT_RUNNER_MODULE,
                       help="Invoke an Ansible module directly without a playbook")

    group.add_argument("-p", "--playbook", default=DEFAULT_RUNNER_PLAYBOOK,
                       help="The name of the playbook to execute")

    group.add_argument("-r", "--role", default=DEFAULT_RUNNER_ROLE,
                       help="Invoke an Ansible role directly without a playbook")

    parser.add_argument("-b", "--binary", default=DEFAULT_RUNNER_BINARY,
                        help="The full path to ansible[-playbook] binary")

    parser.add_argument("--hosts",
                        help="Define the set of hosts to execute against")

    parser.add_argument("-i", "--ident",
                        default=uuid4(),
                        help="An identifier that will be used when generating the"
                             "artifacts directory and can be used to uniquely identify a playbook run")

    parser.add_argument("--rotate-artifacts",
                        default=0,
                        type=int,
                        help="Automatically clean up old artifact directories after a given number has been created, the default is 0 which disables rotation")

    parser.add_argument("--roles-path", default=DEFAULT_ROLES_PATH,
                        help="Path to the Ansible roles directory")

    parser.add_argument("--role-vars",
                        help="Variables to pass to the role at runtime")

    parser.add_argument("--role-skip-facts", action="store_true", default=False,
                        help="Disable fact collection when executing a role directly")

    parser.add_argument("--artifact-dir",
                        help="Optional Path for the artifact root directory, by default it is located inside the private data dir")

    parser.add_argument("--project-dir",
                        help="Optional Path for the location of the playbook content directory, by default this is 'project' inside the private data dir")

    parser.add_argument("--inventory",
                        help="Override the default inventory location in private_data_dir")

    parser.add_argument("--forks",
                        help="Set Ansible concurrency via Forks")

    parser.add_argument("-j", "--json", action="store_true",
                        help="Output the json event structure to stdout instead of Ansible output")

    parser.add_argument("-v", action="count",
                        help="Increase the verbosity with multiple v's (up to 5) of the ansible-playbook output")

    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Disable all output")

    parser.add_argument("--cmdline",
                        help="Command line options to pass to ansible-playbook at execution time")
    parser.add_argument("--debug", action="store_true",
                        help="Enable Runner debug output logging")

    parser.add_argument("--logfile",
                        help="Log output messages to a file")

    parser.add_argument("-a", "--args", dest='module_args',
                        help="Module arguments")

    parser.add_argument("--process-isolation", dest='process_isolation', action="store_true",
                        help="Limits what directories on the filesystem the playbook run has access to, defaults to /tmp")

    parser.add_argument("--process-isolation-executable", dest='process_isolation_executable', default="bwrap",
                        help="Process isolation executable that will be used. Defaults to bwrap")

    parser.add_argument("--process-isolation-path", dest='process_isolation_path', default="/tmp",
                        help="Path that an isolated playbook run will use for staging. Defaults to /tmp")

    parser.add_argument("--process-isolation-hide-paths", dest='process_isolation_hide_paths',
                        help="List of paths on the system that should be hidden from the playbook run")

    parser.add_argument("--process-isolation-show-paths", dest='process_isolation_show_paths',
                        help="List of paths on the system that should be exposed to the playbook run")

    parser.add_argument("--process-isolation-ro-paths", dest='process_isolation_ro_paths',
                        help="List of paths on the system that should be exposed to the playbook run as read-only")

    parser.add_argument("--directory-isolation-base-path", dest='directory_isolation_base_path',
                        help="Copies the project directory to a location in this directory to prevent multiple simultaneous executions from conflicting")

    parser.add_argument("--limit",
                        help="Matches ansible's ``--limit`` parameter to further constrain the inventory to be used")

    args = parser.parse_args(sys_args)

    output.configure()

    # enable or disable debug mode
    output.set_debug('enable' if args.debug else 'disable')

    # set the output logfile
    if args.logfile:
        output.set_logfile(args.logfile)

    output.debug('starting debug logging')

    # get the absolute path for start since it is a daemon
    args.private_data_dir = os.path.abspath(args.private_data_dir)

    pidfile = os.path.join(args.private_data_dir, 'pid')

    try:
        os.makedirs(args.private_data_dir, mode=0o700)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(args.private_data_dir):
            pass
        else:
            raise

    stderr_path = None
    if args.command != 'run':
        stderr_path = os.path.join(args.private_data_dir, 'daemon.log')
        if not os.path.exists(stderr_path):
            os.close(os.open(stderr_path, os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR))

    if args.command in ('start', 'run'):

        if args.command == 'start':
            import daemon
            from daemon.pidfile import TimeoutPIDLockFile
            context = daemon.DaemonContext(pidfile=TimeoutPIDLockFile(pidfile))
        else:
            context = threading.Lock()

        with context:
            with role_manager(args) as args:
                run_options = dict(private_data_dir=args.private_data_dir,
                                   ident=args.ident,
                                   binary=args.binary,
                                   playbook=args.playbook,
                                   module=args.module,
                                   module_args=args.module_args,
                                   host_pattern=args.hosts,
                                   verbosity=args.v,
                                   quiet=args.quiet,
                                   rotate_artifacts=args.rotate_artifacts,
                                   ignore_logging=False,
                                   json_mode=args.json,
                                   inventory=args.inventory,
                                   forks=args.forks,
                                   project_dir=args.project_dir,
                                   roles_path=[args.roles_path] if args.roles_path else None,
                                   process_isolation=args.process_isolation,
                                   process_isolation_executable=args.process_isolation_executable,
                                   process_isolation_path=args.process_isolation_path,
                                   process_isolation_hide_paths=args.process_isolation_hide_paths,
                                   process_isolation_show_paths=args.process_isolation_show_paths,
                                   process_isolation_ro_paths=args.process_isolation_ro_paths,
                                   directory_isolation_base_path=args.directory_isolation_base_path,
                                   limit=args.limit)
                if args.cmdline:
                    run_options['cmdline'] = args.cmdline

                try:
                    res = run(**run_options)
                except Exception:
                    exc = traceback.format_exc()
                    if stderr_path:
                        open(stderr_path, 'w+').write(exc)
                    else:
                        sys.stderr.write(exc)
                    return 1
            return(res.rc)

    try:
        with open(pidfile, 'r') as f:
            pid = int(f.readline())
    except IOError:
        return(1)

    if args.command == 'stop':
        Runner.handle_termination(pid)
        return (0)

    elif args.command == 'is-alive':
        try:
            os.kill(pid, signal.SIG_DFL)
            return(0)
        except OSError:
            return(1)
