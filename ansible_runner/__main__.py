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
import tempfile

from contextlib import contextmanager
from uuid import uuid4

from yaml import safe_dump, safe_load

from ansible_runner import run
from ansible_runner import output
from ansible_runner import cleanup
from ansible_runner.utils import dump_artifact, Bunch, register_for_cleanup
from ansible_runner.utils.capacity import get_cpu_count, get_mem_in_bytes, ensure_uuid
from ansible_runner.utils.importlib_compat import importlib_metadata
from ansible_runner.runner import Runner
from ansible_runner.exceptions import AnsibleRunnerException

VERSION = importlib_metadata.version("ansible_runner")

DEFAULT_ROLES_PATH = os.getenv('ANSIBLE_ROLES_PATH', None)
DEFAULT_RUNNER_BINARY = os.getenv('RUNNER_BINARY', None)
DEFAULT_RUNNER_PLAYBOOK = os.getenv('RUNNER_PLAYBOOK', None)
DEFAULT_RUNNER_ROLE = os.getenv('RUNNER_ROLE', None)
DEFAULT_RUNNER_MODULE = os.getenv('RUNNER_MODULE', None)
DEFAULT_UUID = uuid4()

DEFAULT_CLI_ARGS = {
    "positional_args": (
        (
            ('private_data_dir',),
            dict(
                help="base directory containing the ansible-runner metadata "
                     "(project, inventory, env, etc)"
            ),
        ),
    ),
    "generic_args": (
        (
            ('--version',),
            dict(
                action='version',
                version=VERSION
            ),
        ),
        (
            ("--debug",),
            dict(
                action="store_true",
                help="enable ansible-runner debug output logging (default=False)"
            ),
        ),
        (
            ("--logfile",),
            dict(
                help="log output messages to a file (default=None)"
            ),
        ),
    ),
    "mutually_exclusive_group": (
        (
            ("-p", "--playbook",),
            dict(
                default=DEFAULT_RUNNER_PLAYBOOK,
                help="invoke an Ansible playbook from the ansible-runner project "
                     "(See Ansible Playbook Options below)"
            ),
        ),
        (
            ("-m", "--module",),
            dict(
                default=DEFAULT_RUNNER_MODULE,
                help="invoke an Ansible module directly without a playbook "
                     "(See Ansible Module Options below)"
            ),
        ),
        (
            ("-r", "--role",),
            dict(
                default=DEFAULT_RUNNER_ROLE,
                help="invoke an Ansible role directly without a playbook "
                     "(See Ansible Role Options below)"
            ),
        ),
    ),
    "ansible_group": (
        (
            ("--limit",),
            dict(
                help="matches Ansible's ```--limit``` parameter to further constrain "
                     "the inventory to be used (default=None)"
            ),
        ),
        (
            ("--cmdline",),
            dict(
                help="command line options to pass to ansible-playbook at "
                     "execution time (default=None)"
            ),
        ),
        (
            ("--hosts",),
            dict(
                help="define the set of hosts to execute against (default=None) "
                     "Note: this parameter only works with -m or -r"
            ),
        ),
        (
            ("--forks",),
            dict(
                help="matches Ansible's ```--forks``` parameter to set the number "
                     "of concurrent processes (default=None)"
            ),
        ),
    ),
    "runner_group": (
        # ansible-runner options
        (
            ("-b", "--binary",),
            dict(
                default=DEFAULT_RUNNER_BINARY,
                help="specifies the full path pointing to the Ansible binaries "
                     "(default={})".format(DEFAULT_RUNNER_BINARY)
            ),
        ),
        (
            ("-i", "--ident",),
            dict(
                default=DEFAULT_UUID,
                help="an identifier that will be used when generating the artifacts "
                     "directory and can be used to uniquely identify a playbook run "
                     "(default={})".format(DEFAULT_UUID)
            ),
        ),
        (
            ("--rotate-artifacts",),
            dict(
                default=0,
                type=int,
                help="automatically clean up old artifact directories after a given "
                     "number have been created (default=0, disabled)"
            ),
        ),
        (
            ("--artifact-dir",),
            dict(
                help="optional path for the artifact root directory "
                     "(default=<private_data_dir>/artifacts)"
            ),
        ),
        (
            ("--project-dir",),
            dict(
                help="optional path for the location of the playbook content directory "
                     "(default=<private_data_dir>/project)"
            ),
        ),
        (
            ("--inventory",),
            dict(
                help="optional path for the location of the inventory content directory "
                     "(default=<private_data_dir>/inventory)"
            ),
        ),
        (
            ("-j", "--json",),
            dict(
                action="store_true",
                help="output the JSON event structure to stdout instead of "
                     "Ansible output (default=False)"
            ),
        ),
        (
            ("--omit-event-data",),
            dict(
                action="store_true",
                help="Omits including extra event data in the callback payloads "
                     "or the Runner payload data files "
                     "(status and stdout still included)"
            ),
        ),
        (
            ("--only-failed-event-data",),
            dict(
                action="store_true",
                help="Only adds extra event data for failed tasks in the callback "
                     "payloads or the Runner payload data files "
                     "(status and stdout still included for other events)"
            ),
        ),
        (
            ("--omit-env-files",),
            dict(
                action="store_true",
                dest='suppress_env_files',
                help="Add flag to prevent the writing of the env directory"
            ),
        ),
        (
            ("-q", "--quiet",),
            dict(
                action="store_true",
                help="disable all messages sent to stdout/stderr (default=False)"
            ),
        ),
        (
            ("-v",),
            dict(
                action="count",
                help="increase the verbosity with multiple v's (up to 5) of the "
                     "ansible-playbook output (default=None)"
            ),
        ),
    ),
    "roles_group": (
        (
            ("--roles-path",),
            dict(
                default=DEFAULT_ROLES_PATH,
                help="path used to locate the role to be executed (default=None)"
            ),
        ),
        (
            ("--role-vars",),
            dict(
                help="set of variables to be passed to the role at run time in the "
                     "form of 'key1=value1 key2=value2 keyN=valueN'(default=None)"
            ),
        ),
        (
            ("--role-skip-facts",),
            dict(
                action="store_true",
                default=False,
                help="disable fact collection when the role is executed (default=False)"
            ),
        )
    ),
    "playbook_group": (
        (
            ("--process-isolation",),
            dict(
                dest="process_isolation",
                action="store_true",
                help="Isolate execution. Two methods are supported: (1) using a container engine (e.g. podman or docker) "
                     "to execute **Ansible**. (2) using a sandbox (e.g. bwrap) which will by default restrict access to /tmp "
                     "(default=False)"
            ),
        ),
        (
            ("--process-isolation-executable",),
            dict(
                dest="process_isolation_executable",
                default="podman",
                help="Process isolation executable or container engine used to isolate execution. (default=podman)"
            )
        ),
        (
            ("--process-isolation-path",),
            dict(
                dest="process_isolation_path",
                default="/tmp",
                help="path that an isolated playbook run will use for staging. "
                     "(default=/tmp)"
            )
        ),
        (
            ("--process-isolation-hide-paths",),
            dict(
                dest="process_isolation_hide_paths",
                nargs='*',
                help="list of paths on the system that should be hidden from the "
                     "playbook run (default=None)"
            )
        ),
        (
            ("--process-isolation-show-paths",),
            dict(
                dest="process_isolation_show_paths",
                nargs='*',
                help="list of paths on the system that should be exposed to the "
                     "playbook run (default=None)"
            )
        ),
        (
            ("--process-isolation-ro-paths",),
            dict(
                dest="process_isolation_ro_paths",
                nargs='*',
                help="list of paths on the system that should be exposed to the "
                     "playbook run as read-only (default=None)"
            )
        ),
        (
            ("--directory-isolation-base-path",),
            dict(
                dest="directory_isolation_base_path",
                help="copies the project directory to a location in this directory "
                     "to prevent multiple simultaneous executions from conflicting "
                     "(default=None)"
            )
        )
    ),
    "modules_group": (
        (
            ("-a", "--args",),
            dict(
                dest='module_args',
                help="set of arguments to be passed to the module at run time in the "
                     "form of 'key1=value1 key2=value2 keyN=valueN'(default=None)"
            )
        ),
    ),
    "container_group": (
        (
            ("--container-image",),
            dict(
                dest="container_image",
                default="quay.io/ansible/ansible-runner:devel",
                help="Container image to use when running an ansible task"
            )
        ),
        (
            ("--container-volume-mount",),
            dict(
                dest="container_volume_mounts",
                action='append',
                help="Bind mounts (in the form 'host_dir:/container_dir)'. "
                     "Can be used more than once to create multiple bind mounts."
            )
        ),
        (
            ("--container-option",),
            dict(
                dest="container_options",
                action='append',
                help="Container options to pass to execution engine. "
                     "Can be used more than once to send multiple options."
            )
        ),
    ),
}

logger = logging.getLogger('ansible-runner')


class AnsibleRunnerArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # If no sub command was provided, print common usage then exit
        if 'required: command' in message.lower():
            print_common_usage()

        super(AnsibleRunnerArgumentParser, self).error(message)


@contextmanager
def role_manager(vargs):
    if vargs.get('role'):
        role = {'name': vargs.get('role')}
        if vargs.get('role_vars'):
            role_vars = {}
            for item in vargs['role_vars'].split():
                key, value = item.split('=')
                try:
                    role_vars[key] = ast.literal_eval(value)
                except Exception:
                    role_vars[key] = value
            role['vars'] = role_vars

        kwargs = Bunch(**vargs)
        kwargs.update(private_data_dir=vargs.get('private_data_dir'),
                      json_mode=vargs.get('json'),
                      ignore_logging=False,
                      project_dir=vargs.get('project_dir'),
                      rotate_artifacts=vargs.get('rotate_artifacts'))

        if vargs.get('artifact_dir'):
            kwargs.artifact_dir = vargs.get('artifact_dir')

        if vargs.get('project_dir'):
            project_path = kwargs.project_dir = vargs.get('project_dir')
        else:
            project_path = os.path.join(vargs.get('private_data_dir'), 'project')

        project_exists = os.path.exists(project_path)

        env_path = os.path.join(vargs.get('private_data_dir'), 'env')
        env_exists = os.path.exists(env_path)

        envvars_path = os.path.join(vargs.get('private_data_dir'), 'env/envvars')
        envvars_exists = os.path.exists(envvars_path)

        if vargs.get('cmdline'):
            kwargs.cmdline = vargs.get('cmdline')

        playbook = None
        tmpvars = None

        play = [{'hosts': vargs.get('hosts') if vargs.get('hosts') is not None else "all",
                 'gather_facts': not vargs.get('role_skip_facts'),
                 'roles': [role]}]

        filename = str(uuid4().hex)

        playbook = dump_artifact(json.dumps(play), project_path, filename)
        kwargs.playbook = playbook
        output.debug('using playbook file %s' % playbook)

        if vargs.get('inventory'):
            inventory_file = os.path.join(vargs.get('private_data_dir'), 'inventory', vargs.get('inventory'))
            if not os.path.exists(inventory_file):
                raise AnsibleRunnerException('location specified by --inventory does not exist')
            kwargs.inventory = inventory_file
            output.debug('using inventory file %s' % inventory_file)

        roles_path = vargs.get('roles_path') or os.path.join(vargs.get('private_data_dir'), 'roles')
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
        kwargs = vargs

    yield kwargs

    if vargs.get('role'):
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


def add_args_to_parser(parser, args):
    """
    Traverse a tuple of argments to add to a parser

    :param argparse.ArgumentParser parser: Instance of a parser, subparser, or argument group

    :param tuple args: Tuple of tuples, format ((arg1, arg2), {'kwarg1':'val1'},)

    :returns: None
    """
    for arg in args:
        parser.add_argument(*arg[0], **arg[1])


def main(sys_args=None):
    """Main entry point for ansible-runner executable

    When the ```ansible-runner``` command is executed, this function
    is the main entry point that is called and executed.

    :param list sys_args: List of arguments to be parsed by the parser

    :returns: an instance of SystemExit
    :rtype: SystemExit
    """

    parser = AnsibleRunnerArgumentParser(
        prog='ansible-runner',
        description="Use 'ansible-runner' (with no arguments) to see basic usage"
    )
    subparser = parser.add_subparsers(
        help="Command to invoke",
        dest='command',
        description="COMMAND PRIVATE_DATA_DIR [ARGS]"
    )
    add_args_to_parser(parser, DEFAULT_CLI_ARGS['generic_args'])
    subparser.required = True

    # positional options
    run_subparser = subparser.add_parser(
        'run',
        help="Run ansible-runner in the foreground"
    )
    add_args_to_parser(run_subparser, DEFAULT_CLI_ARGS['positional_args'])
    add_args_to_parser(run_subparser, DEFAULT_CLI_ARGS['playbook_group'])
    start_subparser = subparser.add_parser(
        'start',
        help="Start an ansible-runner process in the background"
    )
    add_args_to_parser(start_subparser, DEFAULT_CLI_ARGS['positional_args'])
    add_args_to_parser(start_subparser, DEFAULT_CLI_ARGS['playbook_group'])
    stop_subparser = subparser.add_parser(
        'stop',
        help="Stop an ansible-runner process that's running in the background"
    )
    add_args_to_parser(stop_subparser, DEFAULT_CLI_ARGS['positional_args'])
    isalive_subparser = subparser.add_parser(
        'is-alive',
        help="Check if a an ansible-runner process in the background is still running."
    )
    add_args_to_parser(isalive_subparser, DEFAULT_CLI_ARGS['positional_args'])

    # streaming commands
    transmit_subparser = subparser.add_parser(
        'transmit',
        help="Send a job to a remote ansible-runner process"
    )
    add_args_to_parser(transmit_subparser, DEFAULT_CLI_ARGS['positional_args'])

    worker_subparser = subparser.add_parser(
        'worker',
        help="Execute work streamed from a controlling instance"
    )
    worker_subcommands = worker_subparser.add_subparsers(
        help="Sub-sub command to invoke",
        dest='worker_subcommand',
        description="ansible-runner worker [sub-sub-command]",
    )
    cleanup_command = worker_subcommands.add_parser(
        'cleanup',
        help="Cleanup private_data_dir patterns from prior jobs and supporting temporary folders.",
    )
    cleanup.add_cleanup_args(cleanup_command)

    worker_subparser.add_argument(
        "--private-data-dir",
        help="base directory containing the ansible-runner metadata "
             "(project, inventory, env, etc)",
    )

    worker_subparser.add_argument(
        "--worker-info",
        dest="worker_info",
        action="store_true",
        help="show the execution node's Ansible Runner version along with its memory and CPU capacities"
    )
    worker_subparser.add_argument(
        "--delete",
        dest="delete_directory",
        action="store_true",
        default=False,
        help=(
            "Delete existing folder (and everything in it) in the location specified by --private-data-dir. "
            "The directory will be re-populated when the streamed data is unpacked. "
            "Using this will also assure that the directory is deleted when the job finishes."
        )
    )
    worker_subparser.add_argument(
        "--keepalive-seconds",
        dest="keepalive_seconds",
        default=None,
        type=int,
        help=(
            "Emit a synthetic keepalive event every N seconds of idle. (default=0, disabled)"
        )
    )
    process_subparser = subparser.add_parser(
        'process',
        help="Receive the output of remote ansible-runner work and distribute the results"
    )
    add_args_to_parser(process_subparser, DEFAULT_CLI_ARGS['positional_args'])
    process_subparser.add_argument(
        "-i", "--ident",
        default=None,
        help=(
            "An identifier to use as a subdirectory when saving artifacts. "
            "Generally intended to match the --ident passed to the transmit command."
        )
    )

    # generic args for all subparsers
    add_args_to_parser(run_subparser, DEFAULT_CLI_ARGS['generic_args'])
    add_args_to_parser(start_subparser, DEFAULT_CLI_ARGS['generic_args'])
    add_args_to_parser(stop_subparser, DEFAULT_CLI_ARGS['generic_args'])
    add_args_to_parser(isalive_subparser, DEFAULT_CLI_ARGS['generic_args'])
    add_args_to_parser(transmit_subparser, DEFAULT_CLI_ARGS['generic_args'])
    add_args_to_parser(worker_subparser, DEFAULT_CLI_ARGS['generic_args'])
    add_args_to_parser(process_subparser, DEFAULT_CLI_ARGS['generic_args'])

    # runner group
    ansible_runner_group_options = (
        "Ansible Runner Options",
        "configuration options for controlling the ansible-runner "
        "runtime environment.",
    )
    base_runner_group = parser.add_argument_group(*ansible_runner_group_options)
    run_runner_group = run_subparser.add_argument_group(*ansible_runner_group_options)
    start_runner_group = start_subparser.add_argument_group(*ansible_runner_group_options)
    stop_runner_group = stop_subparser.add_argument_group(*ansible_runner_group_options)
    isalive_runner_group = isalive_subparser.add_argument_group(*ansible_runner_group_options)
    transmit_runner_group = transmit_subparser.add_argument_group(*ansible_runner_group_options)
    add_args_to_parser(base_runner_group, DEFAULT_CLI_ARGS['runner_group'])
    add_args_to_parser(run_runner_group, DEFAULT_CLI_ARGS['runner_group'])
    add_args_to_parser(start_runner_group, DEFAULT_CLI_ARGS['runner_group'])
    add_args_to_parser(stop_runner_group, DEFAULT_CLI_ARGS['runner_group'])
    add_args_to_parser(isalive_runner_group, DEFAULT_CLI_ARGS['runner_group'])
    add_args_to_parser(transmit_runner_group, DEFAULT_CLI_ARGS['runner_group'])

    # mutually exclusive group
    run_mutually_exclusive_group = run_subparser.add_mutually_exclusive_group()
    start_mutually_exclusive_group = start_subparser.add_mutually_exclusive_group()
    stop_mutually_exclusive_group = stop_subparser.add_mutually_exclusive_group()
    isalive_mutually_exclusive_group = isalive_subparser.add_mutually_exclusive_group()
    transmit_mutually_exclusive_group = transmit_subparser.add_mutually_exclusive_group()
    add_args_to_parser(run_mutually_exclusive_group, DEFAULT_CLI_ARGS['mutually_exclusive_group'])
    add_args_to_parser(start_mutually_exclusive_group, DEFAULT_CLI_ARGS['mutually_exclusive_group'])
    add_args_to_parser(stop_mutually_exclusive_group, DEFAULT_CLI_ARGS['mutually_exclusive_group'])
    add_args_to_parser(isalive_mutually_exclusive_group, DEFAULT_CLI_ARGS['mutually_exclusive_group'])
    add_args_to_parser(transmit_mutually_exclusive_group, DEFAULT_CLI_ARGS['mutually_exclusive_group'])

    # ansible options
    ansible_options = (
        "Ansible Options",
        "control the ansible[-playbook] execution environment",
    )
    run_ansible_group = run_subparser.add_argument_group(*ansible_options)
    start_ansible_group = start_subparser.add_argument_group(*ansible_options)
    stop_ansible_group = stop_subparser.add_argument_group(*ansible_options)
    isalive_ansible_group = isalive_subparser.add_argument_group(*ansible_options)
    transmit_ansible_group = transmit_subparser.add_argument_group(*ansible_options)
    add_args_to_parser(run_ansible_group, DEFAULT_CLI_ARGS['ansible_group'])
    add_args_to_parser(start_ansible_group, DEFAULT_CLI_ARGS['ansible_group'])
    add_args_to_parser(stop_ansible_group, DEFAULT_CLI_ARGS['ansible_group'])
    add_args_to_parser(isalive_ansible_group, DEFAULT_CLI_ARGS['ansible_group'])
    add_args_to_parser(transmit_ansible_group, DEFAULT_CLI_ARGS['ansible_group'])

    # roles group
    roles_group_options = (
        "Ansible Role Options",
        "configuration options for directly executing Ansible roles",
    )
    run_roles_group = run_subparser.add_argument_group(*roles_group_options)
    start_roles_group = start_subparser.add_argument_group(*roles_group_options)
    stop_roles_group = stop_subparser.add_argument_group(*roles_group_options)
    isalive_roles_group = isalive_subparser.add_argument_group(*roles_group_options)
    transmit_roles_group = transmit_subparser.add_argument_group(*roles_group_options)
    add_args_to_parser(run_roles_group, DEFAULT_CLI_ARGS['roles_group'])
    add_args_to_parser(start_roles_group, DEFAULT_CLI_ARGS['roles_group'])
    add_args_to_parser(stop_roles_group, DEFAULT_CLI_ARGS['roles_group'])
    add_args_to_parser(isalive_roles_group, DEFAULT_CLI_ARGS['roles_group'])
    add_args_to_parser(transmit_roles_group, DEFAULT_CLI_ARGS['roles_group'])

    # modules groups

    modules_group_options = (
        "Ansible Module Options",
        "configuration options for directly executing Ansible modules",
    )
    run_modules_group = run_subparser.add_argument_group(*modules_group_options)
    start_modules_group = start_subparser.add_argument_group(*modules_group_options)
    stop_modules_group = stop_subparser.add_argument_group(*modules_group_options)
    isalive_modules_group = isalive_subparser.add_argument_group(*modules_group_options)
    transmit_modules_group = transmit_subparser.add_argument_group(*modules_group_options)
    add_args_to_parser(run_modules_group, DEFAULT_CLI_ARGS['modules_group'])
    add_args_to_parser(start_modules_group, DEFAULT_CLI_ARGS['modules_group'])
    add_args_to_parser(stop_modules_group, DEFAULT_CLI_ARGS['modules_group'])
    add_args_to_parser(isalive_modules_group, DEFAULT_CLI_ARGS['modules_group'])
    add_args_to_parser(transmit_modules_group, DEFAULT_CLI_ARGS['modules_group'])

    # container group
    container_group_options = (
        "Ansible Container Options",
        "configuration options for executing Ansible playbooks",
    )
    run_container_group = run_subparser.add_argument_group(*container_group_options)
    start_container_group = start_subparser.add_argument_group(*container_group_options)
    stop_container_group = stop_subparser.add_argument_group(*container_group_options)
    isalive_container_group = isalive_subparser.add_argument_group(*container_group_options)
    transmit_container_group = transmit_subparser.add_argument_group(*container_group_options)
    add_args_to_parser(run_container_group, DEFAULT_CLI_ARGS['container_group'])
    add_args_to_parser(start_container_group, DEFAULT_CLI_ARGS['container_group'])
    add_args_to_parser(stop_container_group, DEFAULT_CLI_ARGS['container_group'])
    add_args_to_parser(isalive_container_group, DEFAULT_CLI_ARGS['container_group'])
    add_args_to_parser(transmit_container_group, DEFAULT_CLI_ARGS['container_group'])

    args = parser.parse_args(sys_args)

    vargs = vars(args)

    if vargs.get('command') == 'worker':
        if vargs.get('worker_subcommand') == 'cleanup':
            cleanup.run_cleanup(vargs)
            parser.exit(0)
        if vargs.get('worker_info'):
            cpu = get_cpu_count()
            mem = get_mem_in_bytes()
            errors = []
            uuid = ensure_uuid()
            if not isinstance(mem, int):
                errors.append(mem)
                mem = None
            if "Could not find" in uuid:
                errors.append(uuid)
                uuid = None
            info = {'errors': errors,
                    'mem_in_bytes': mem,
                    'cpu_count': cpu,
                    'runner_version': VERSION,
                    'uuid': uuid,
                    }
            print(safe_dump(info, default_flow_style=True))
            parser.exit(0)

        private_data_dir = vargs.get('private_data_dir')
        delete_directory = vargs.get('delete_directory', False)
        if private_data_dir and delete_directory:
            shutil.rmtree(private_data_dir, ignore_errors=True)
            register_for_cleanup(private_data_dir)
        elif private_data_dir is None:
            temp_private_dir = tempfile.mkdtemp()
            vargs['private_data_dir'] = temp_private_dir
            register_for_cleanup(temp_private_dir)

    if vargs.get('command') == 'process':
        # the process command is the final destination of artifacts, user expects private_data_dir to not be cleaned up
        if not vargs.get('private_data_dir'):
            temp_private_dir = tempfile.mkdtemp()
            vargs['private_data_dir'] = temp_private_dir

    if vargs.get('command') in ('start', 'run', 'transmit'):
        if vargs.get('hosts') and not (vargs.get('module') or vargs.get('role')):
            parser.exit(status=1, message="The --hosts option can only be used with -m or -r\n")
        if not (vargs.get('module') or vargs.get('role')) and not vargs.get('playbook'):
            parser.exit(status=1, message="The -p option must be specified when not using -m or -r\n")

    output.configure()

    # enable or disable debug mode
    output.set_debug('enable' if vargs.get('debug') else 'disable')

    # set the output logfile
    if ('logfile' in args) and vargs.get('logfile'):
        output.set_logfile(vargs.get('logfile'))

    output.debug('starting debug logging')

    # get the absolute path for start since it is a daemon
    vargs['private_data_dir'] = os.path.abspath(vargs.get('private_data_dir'))

    pidfile = os.path.join(vargs.get('private_data_dir'), 'pid')

    try:
        os.makedirs(vargs.get('private_data_dir'), mode=0o700)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(vargs.get('private_data_dir')):
            pass
        else:
            raise

    stderr_path = None
    context = None
    if vargs.get('command') not in ('run', 'transmit', 'worker'):
        stderr_path = os.path.join(vargs.get('private_data_dir'), 'daemon.log')
        if not os.path.exists(stderr_path):
            os.close(os.open(stderr_path, os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR))

    if vargs.get('command') in ('start', 'run', 'transmit', 'worker', 'process'):

        if vargs.get('command') == 'start':
            import daemon
            from daemon.pidfile import TimeoutPIDLockFile
            context = daemon.DaemonContext(pidfile=TimeoutPIDLockFile(pidfile))
        else:
            context = threading.Lock()

        streamer = None
        if vargs.get('command') in ('transmit', 'worker', 'process'):
            streamer = vargs.get('command')

        with context:
            with role_manager(vargs) as vargs:
                run_options = dict(private_data_dir=vargs.get('private_data_dir'),
                                   ident=vargs.get('ident'),
                                   binary=vargs.get('binary'),
                                   playbook=vargs.get('playbook'),
                                   module=vargs.get('module'),
                                   module_args=vargs.get('module_args'),
                                   host_pattern=vargs.get('hosts'),
                                   verbosity=vargs.get('v'),
                                   quiet=vargs.get('quiet'),
                                   rotate_artifacts=vargs.get('rotate_artifacts'),
                                   ignore_logging=False,
                                   json_mode=vargs.get('json'),
                                   omit_event_data=vargs.get('omit_event_data'),
                                   only_failed_event_data=vargs.get('only_failed_event_data'),
                                   inventory=vargs.get('inventory'),
                                   forks=vargs.get('forks'),
                                   project_dir=vargs.get('project_dir'),
                                   artifact_dir=vargs.get('artifact_dir'),
                                   roles_path=[vargs.get('roles_path')] if vargs.get('roles_path') else None,
                                   process_isolation=vargs.get('process_isolation'),
                                   process_isolation_executable=vargs.get('process_isolation_executable'),
                                   process_isolation_path=vargs.get('process_isolation_path'),
                                   process_isolation_hide_paths=vargs.get('process_isolation_hide_paths'),
                                   process_isolation_show_paths=vargs.get('process_isolation_show_paths'),
                                   process_isolation_ro_paths=vargs.get('process_isolation_ro_paths'),
                                   container_image=vargs.get('container_image'),
                                   container_volume_mounts=vargs.get('container_volume_mounts'),
                                   container_options=vargs.get('container_options'),
                                   directory_isolation_base_path=vargs.get('directory_isolation_base_path'),
                                   cmdline=vargs.get('cmdline'),
                                   limit=vargs.get('limit'),
                                   streamer=streamer,
                                   suppress_env_files=vargs.get("suppress_env_files"),
                                   keepalive_seconds=vargs.get("keepalive_seconds"),
                                   )
                try:
                    res = run(**run_options)
                except Exception:
                    exc = traceback.format_exc()
                    if stderr_path:
                        open(stderr_path, 'w+').write(exc)
                    else:
                        sys.stderr.write(exc)
                    return 1
            return res.rc

    try:
        with open(pidfile, 'r') as f:
            pid = int(f.readline())
    except IOError:
        return 1

    if vargs.get('command') == 'stop':
        Runner.handle_termination(pid, pidfile=pidfile)
        return 0

    elif vargs.get('command') == 'is-alive':
        try:
            os.kill(pid, signal.SIG_DFL)
            return 0
        except OSError:
            return 1


if __name__ == '__main__':
    sys.exit(main())
