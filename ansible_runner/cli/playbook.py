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
import os
import stat
import signal

from ansible_runner import interface
from ansible_runner.runner import Runner
from ansible_runner.helpers import fork_process
from ansible_runner.cli.common import add_runner_group, add_ansible_group
from ansible_runner.exceptions import AnsibleRunnerCliError


def init(parser):

    parser.add_argument(
        "directive",
        choices=["start", "stop", "is-alive"],
        help="command directive to issue to Ansible Runner"
    )

    group = parser.add_argument_group(
        "Ansible Runner Playbook Options",
        "configuation options for executing Ansible playbooks"
    )

    group.add_argument(
        "--name",
        default="main.yml",
        help="name of the playbook to invoke (must be present in "
             "the`project` folder (default=main.yml)"
    )

    parser.add_argument(
        "--private-data-dir",
        default=os.getcwd(),
        help="path to the Ansible Runner private data directory "
             "where the playbook is contained (default=$PWD)"
    )

    group.add_argument(
        "--detach",
        action="store_true",
        help="detach from the running instance and invoke the "
             "playbook in the background"
    )

    group.add_argument(
        "--process-isolation",
        action="store_true",
        help="limits what directories on the filesystem the playbook run "
             "has access to, defaults to /tmp (default=False)"
    )

    group.add_argument(
        "--process-isolation-executable",
        default="bwrap",
        help="process isolation executable that will be used. (default=bwrap)"
    )

    group.add_argument(
        "--process-isolation-path",
        default="/tmp",
        help="path that an isolated playbook run will use for staging. "
             "(default=/tmp)"
    )

    group.add_argument(
        "--process-isolation-hide-paths",
        help="list of paths on the system that should be hidden from the "
             "playbook run (default=None)"
    )

    group.add_argument(
        "--process-isolation-show-paths",
        help="list of paths on the system that should be exposed to the "
             "playbook run (default=None)"
    )

    group.add_argument(
        "--process-isolation-ro-paths",
        help="list of paths on the system that should be exposed to the "
             "playbook run as read-only (default=None)"
    )

    group.add_argument(
        "--directory-isolation-base-path",
        help="copies the project directory to a location in this directory "
             "to prevent multiple simultaneous executions from conflicting "
             "(default=None)"
    )

    add_runner_group(parser)
    add_ansible_group(parser)


def run(ns):

    # get the absolute path for start since it is a daemon
    private_data_dir = os.path.abspath(ns.private_data_dir)

    if not os.path.exists(private_data_dir) or not os.path.isdir(private_data_dir):
        raise AnsibleRunnerCliError('playbook', 'private_data_dir is invalid')

    pidfile = os.path.join(private_data_dir, 'pid')

    stderr_path = None
    if ns.directive != 'run':
        stderr_path = os.path.join(private_data_dir, 'daemon.log')
        if not os.path.exists(stderr_path):
            os.close(os.open(stderr_path, os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR))


    if ns.directive == 'start':

        kwargs = {
            'playbook': ns.name,
            'private_data_dir': private_data_dir,

            'ident': ns.ident,
            'binary': ns.binary,
            'rotate_artifacts': ns.rotate_artifacts,

            'inventory': ns.inventory,
            'project_dir': ns.project_dir,

            'host_pattern': ns.hosts,
            'forks': ns.forks,
            'limit': ns.limit,

            'process_isolation': ns.process_isolation,
            'process_isolation_executable': ns.process_isolation_executable,
            'process_isolation_path': ns.process_isolation_path,
            'process_isolation_hide_paths': ns.process_isolation_hide_paths,
            'process_isolation_show_paths': ns.process_isolation_show_paths,
            'process_isolation_ro_paths': ns.process_isolation_ro_paths,
            'directory_isolation_base_path': ns.directory_isolation_base_path,

            'verbosity': ns.verbose,
            'quiet': ns.quiet,
            'ignore_logging': False,
            'json_mode': ns.json,
        }

        if ns.detach is True:
            # handle forking here
            pid = fork_process()
            if pid == 0:
                with open(pidfile, 'w') as f:
                    f.write(str(os.getpid()))
                runner = interface.run(**kwargs)
                open(stderr_path, 'w+').write(runner.status)
                os.remove(pidfile)
            else:
                rc = 0

        else:
            runner = interface.run(**kwargs)

            for line in runner.stdout:
                print(line.strip())

            rc = runner.rc

    elif ns.directive in ('stop', 'is-alive'):

        if os.path.exists(pidfile):
            with open(pidfile, 'r') as f:
                pid = int(f.readline())

            if ns.directive == 'stop':
                Runner.handle_termination(pid)
                os.remove(pidfile)
                rc = 0

            elif ns.directive == 'is-alive':
                try:
                    os.kill(pid, signal.SIG_DFL)
                    rc = 0
                except OSError:
                    rc = 1

    return rc
