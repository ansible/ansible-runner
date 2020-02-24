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
import textwrap

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
DEFAULT_UUID = uuid4()

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


def print_common_usage():
    print(textwrap.dedent("""
        These are common Ansible Runner commands:

            execute a playbook contained in an ansible-runner directory:

                ansible-runner run /tmp/private -p playbook.yml
                ansible-runner start /tmp/private -p playbook.yml
                ansible-runner stop /tmp/private
                ansible-runner is-alive /tmp/private

            directly execute ansible primitives:

                ansible-runner run . -r role_name --hosts myhost
                ansible-runner run . -m command -a "ls -l" --hosts myhost

        `ansible-runner --help` list of optional command line arguments
    """))


def main(sys_args=None):
    """Main entry point for ansible-runner executable

    When the ```ansible-runner``` command is executed, this function
    is the main entry point that is called and executed.

    :param sys_args: List of arguments to be parsed by the parser
    :type sys_args: list

    :returns: an instance of SystemExit
    :rtype: SystemExit
    """
    parser = argparse.ArgumentParser(
        description="Use 'ansible-runner' (with no arguments) to see basic usage"
    )

    parser.add_argument(
        '--version',
        action='version',
        version=VERSION
    )

    # positional options

    parser.add_argument(
        "command",
        choices=["run", "start", "stop", "is-alive"],
        metavar="COMMAND",
        help="command directive for controlling ansible-runner execution "
             "(one of 'run', 'start', 'stop', 'is-alive')"
        #help="command directive controlling ansible-runner execution"
    )

    parser.add_argument(
        'private_data_dir',
        help="base directory cotnaining the ansible-runner metadata "
             "(project, inventory, env, etc)"
    )

    # mutually exclusive group

    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "-p", "--playbook",
        default=DEFAULT_RUNNER_PLAYBOOK,
        help="invoke an Ansible playbook from the ansible-runner project "
             "(See Ansible Playbook Options below)"
    )

    group.add_argument(
        "-m", "--module",
        default=DEFAULT_RUNNER_MODULE,
        help="invoke an Ansible module directly without a playbook "
             "(See Ansible Module Options below)"
    )

    group.add_argument(
        "-r", "--role",
        default=DEFAULT_RUNNER_ROLE,
        help="invoke an Ansible role directly without a playbook "
             "(See Ansible Role Options below)"
    )

    # ansible-runner options

    runner_group = parser.add_argument_group(
        "Ansible Runner Options",
        "configuration options for controlling the ansible-runner "
        "runtime environment."
    )

    runner_group.add_argument(
        "--debug",
        action="store_true",
        help="enable ansible-runner debug output logging (default=False)"
    )

    runner_group.add_argument(
        "--logfile",
        help="log output messages to a file (default=None)"
    )

    runner_group.add_argument(
        "-b", "--binary",
        default=DEFAULT_RUNNER_BINARY,
        help="specifies the full path pointing to the Ansible binaries "
              "(default={})".format(DEFAULT_RUNNER_BINARY)
    )

    runner_group.add_argument(
        "-i", "--ident",
        default=DEFAULT_UUID,
        help="an identifier that will be used when generating the artifacts "
             "directory and can be used to uniquely identify a playbook run "
             "(default={})".format(DEFAULT_UUID)
    )

    runner_group.add_argument(
        "--rotate-artifacts",
        default=0,
        type=int,
        help="automatically clean up old artifact directories after a given "
             "number have been created (default=0, disabled)"
    )

    runner_group.add_argument(
        "--artifact-dir",
        help="optional path for the artifact root directory "
             "(default=<private_data_dir>/artifacts)"
    )

    runner_group.add_argument(
        "--project-dir",
        help="optional path for the location of the playbook content directory "
             "(default=<private_data_dir/project)"
    )

    runner_group.add_argument(
        "--inventory",
        help="optional path for the location of the inventory content directory "
             "(default=<private_data_dir>/inventory)"
    )

    runner_group.add_argument(
        "-j", "--json",
        action="store_true",
        help="output the JSON event structure to stdout instead of "
             "Ansible output (default=False)"
    )

    runner_group.add_argument(
        "--omit-event-data",
        action="store_true",
        help="Omits including extra event data in the callback payloads "
             "or the Runner payload data files "
             "(status and stdout still included)"
    )

    runner_group.add_argument(
        "--only-failed-event-data",
        action="store_true",
        help="Only adds extra event data for failed tasks in the callback "
             "payloads or the Runner payload data files "
             "(status and stdout still included for other events)"
    )

    runner_group.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="disable all messages sent to stdout/stderr (default=False)"
    )

    runner_group.add_argument(
        "-v",
        action="count",
        help="increase the verbosity with multiple v's (up to 5) of the "
             "ansible-playbook output (default=None)"
    )

    # ansible options

    ansible_group = parser.add_argument_group(
        "Ansible Options",
        "control the ansible[-playbook] execution environment"
    )

    ansible_group.add_argument(
        "--limit",
        help="matches Ansible's ```--limit``` parameter to further constrain "
             "the inventory to be used (default=None)"
    )

    ansible_group.add_argument(
        "--cmdline",
        help="command line options to pass to ansible-playbook at "
             "execution time (default=None)"
    )

    ansible_group.add_argument(
        "--hosts",
        help="define the set of hosts to execute against (default=None) "
             "Note: this parameter only works with -m or -r"
    )

    ansible_group.add_argument(
        "--forks",
        help="matches Ansible's ```--forks``` parameter to set the number "
             "of conconurent processes (default=None)"
    )

    # roles group

    roles_group = parser.add_argument_group(
        "Ansible Role Options",
        "configuration options for directly executing Ansible roles"
    )

    roles_group.add_argument(
        "--roles-path",
        default=DEFAULT_ROLES_PATH,
        help="path used to locate the role to be executed (default=None)"
    )

    roles_group.add_argument(
        "--role-vars",
        help="set of variables to be passed to the role at run time in the "
             "form of 'key1=value1 key2=value2 keyN=valueN'(default=None)"
    )

    roles_group.add_argument(
        "--role-skip-facts",
        action="store_true",
        default=False,
        help="disable fact collection when the role is executed (default=False)"
    )

    # modules groups

    modules_group = parser.add_argument_group(
        "Ansible Module Options",
        "configuration options for directly executing Ansible modules"
    )

    modules_group.add_argument(
        "-a", "--args",
        dest='module_args',
        help="set of arguments to be passed to the module at run time in the "
             "form of 'key1=value1 key2=value2 keyN=valueN'(default=None)"
    )

    # playbook options
    playbook_group = parser.add_argument_group(
        "Ansible Playbook Options",
        "configuation options for executing Ansible playbooks"
    )

    playbook_group.add_argument(
        "--process-isolation",
        dest="process_isolation",
        action="store_true",
        help="limits what directories on the filesystem the playbook run "
             "has access to, defaults to /tmp (default=False)"
    )

    playbook_group.add_argument(
        "--process-isolation-executable",
        dest="process_isolation_executable",
        default="bwrap",
        help="process isolation executable that will be used. (default=bwrap)"
    )

    playbook_group.add_argument(
        "--process-isolation-path",
        dest="process_isolation_path",
        default="/tmp",
        help="path that an isolated playbook run will use for staging. "
             "(default=/tmp)"
    )

    playbook_group.add_argument(
        "--process-isolation-hide-paths",
        dest="process_isolation_hide_paths",
        nargs='*',
        help="list of paths on the system that should be hidden from the "
             "playbook run (default=None)"
    )

    playbook_group.add_argument(
        "--process-isolation-show-paths",
        dest="process_isolation_show_paths",
        nargs='*',
        help="list of paths on the system that should be exposed to the "
             "playbook run (default=None)"
    )

    playbook_group.add_argument(
        "--process-isolation-ro-paths",
        dest="process_isolation_ro_paths",
        nargs='*',
        help="list of paths on the system that should be exposed to the "
             "playbook run as read-only (default=None)"
    )

    playbook_group.add_argument(
        "--directory-isolation-base-path",
        dest="directory_isolation_base_path",
        help="copies the project directory to a location in this directory "
             "to prevent multiple simultaneous executions from conflicting "
             "(default=None)"
    )

    playbook_group.add_argument(
        "--resource-profiling",
        dest='resource_profiling',
        action="store_true",
        help="Records resource utilization during playbook execution")

    playbook_group.add_argument(
        "--resource-profiling-base-cgroup",
        dest='resource_profiling_base_cgroup',
        default="ansible-runner",
        help="Top-level cgroup used to collect information on resource utilization. Defaults to ansible-runner")

    playbook_group.add_argument(
        "--resource-profiling-cpu-poll-interval",
        dest='resource_profiling_cpu_poll_interval',
        default=0.25,
        help="Interval (in seconds) between CPU polling for determining CPU usage. Defaults to 0.25")

    playbook_group.add_argument(
        "--resource-profiling-memory-poll-interval",
        dest='resource_profiling_memory_poll_interval',
        default=0.25,
        help="Interval (in seconds) between memory polling for determining memory usage. Defaults to 0.25")

    playbook_group.add_argument(
        "--resource-profiling-pid-poll-interval",
        dest='resource_profiling_pid_poll_interval',
        default=0.25,
        help="Interval (in seconds) between polling PID count for determining number of processes used. Defaults to 0.25")

    playbook_group.add_argument(
        "--resource-profiling-results-dir",
        dest='resource_profiling_results_dir',
        help="Directory where profiling data files should be saved. Defaults to None (profiling_data folder under private data dir is used in this case).")

    if len(sys.argv) == 1:
        parser.print_usage()
        print_common_usage()
        parser.exit(status=0)

    args = parser.parse_args(sys_args)

    if args.command in ('start', 'run'):
        if args.hosts and not (args.module or args.role):
            parser.exit(status=1, message="The --hosts option can only be used with -m or -r\n")
        if not (args.module or args.role) and not args.playbook:
            parser.exit(status=1, message="The -p option must be specified when not using -m or -r\n")

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
    context = None
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
                                   omit_event_data=args.omit_event_data,
                                   only_failed_event_data=args.only_failed_event_data,
                                   inventory=args.inventory,
                                   forks=args.forks,
                                   project_dir=args.project_dir,
                                   artifact_dir=args.artifact_dir,
                                   roles_path=[args.roles_path] if args.roles_path else None,
                                   process_isolation=args.process_isolation,
                                   process_isolation_executable=args.process_isolation_executable,
                                   process_isolation_path=args.process_isolation_path,
                                   process_isolation_hide_paths=args.process_isolation_hide_paths,
                                   process_isolation_show_paths=args.process_isolation_show_paths,
                                   process_isolation_ro_paths=args.process_isolation_ro_paths,
                                   directory_isolation_base_path=args.directory_isolation_base_path,
                                   resource_profiling=args.resource_profiling,
                                   resource_profiling_base_cgroup=args.resource_profiling_base_cgroup,
                                   resource_profiling_cpu_poll_interval=args.resource_profiling_cpu_poll_interval,
                                   resource_profiling_memory_poll_interval=args.resource_profiling_memory_poll_interval,
                                   resource_profiling_pid_poll_interval=args.resource_profiling_pid_poll_interval,
                                   resource_profiling_results_dir=args.resource_profiling_results_dir,
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
        Runner.handle_termination(pid, pidfile=pidfile)
        return (0)

    elif args.command == 'is-alive':
        try:
            os.kill(pid, signal.SIG_DFL)
            return(0)
        except OSError:
            return(1)
