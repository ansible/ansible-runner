# Copyright (c) 2016 Ansible by Red Hat, Inc.
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
import sys
import threading
import logging

from ansible_runner import output
from ansible_runner.runner_config import RunnerConfig
from ansible_runner.runner import Runner
from ansible_runner.streaming import Transmitter, Worker, Processor
from ansible_runner.utils import (
    dump_artifacts,
    check_isolation_executable_installed,
)

logging.getLogger('ansible-runner').addHandler(logging.NullHandler())


def init_runner(**kwargs):
    '''
    Initialize the Runner() instance

    This function will properly initialize both run() and run_async()
    functions in the same way and return a value instance of Runner.

    See parameters given to :py:func:`ansible_runner.interface.run`
    '''
    # If running via the transmit-worker-process method, we must only extract things as read-only
    # inside of one of these commands. That could be either transmit or worker.
    if not kwargs.get('cli_execenv_cmd') and (kwargs.get('streamer') not in ('worker', 'process')):
        dump_artifacts(kwargs)

    if kwargs.get('streamer'):
        # undo any full paths that were dumped by dump_artifacts above in the streamer case
        private_data_dir = kwargs['private_data_dir']
        project_dir = os.path.join(private_data_dir, 'project')

        playbook_path = kwargs.get('playbook') or ''
        if os.path.isabs(playbook_path) and playbook_path.startswith(project_dir):
            kwargs['playbook'] = os.path.relpath(playbook_path, project_dir)

        inventory_path = kwargs.get('inventory') or ''
        if os.path.isabs(inventory_path) and inventory_path.startswith(private_data_dir):
            kwargs['inventory'] = os.path.relpath(inventory_path, private_data_dir)

        roles_path = kwargs.get('envvars', {}).get('ANSIBLE_ROLES_PATH') or ''
        if os.path.isabs(roles_path) and roles_path.startswith(private_data_dir):
            kwargs['envvars']['ANSIBLE_ROLES_PATH'] = os.path.relpath(roles_path, private_data_dir)

    debug = kwargs.pop('debug', None)
    logfile = kwargs.pop('logfile', None)

    if not kwargs.pop("ignore_logging", True):
        output.configure()
        if debug in (True, False):
            output.set_debug('enable' if debug is True else 'disable')

        if logfile:
            output.set_logfile(logfile)

    if kwargs.get("process_isolation", False):
        pi_executable = kwargs.get("process_isolation_executable", "podman")
        if not check_isolation_executable_installed(pi_executable):
            print(f'Unable to find process isolation executable: {pi_executable}')
            sys.exit(1)

    event_callback_handler = kwargs.pop('event_handler', None)
    status_callback_handler = kwargs.pop('status_handler', None)
    artifacts_handler = kwargs.pop('artifacts_handler', None)
    cancel_callback = kwargs.pop('cancel_callback', None)
    finished_callback = kwargs.pop('finished_callback', None)

    streamer = kwargs.pop('streamer', None)
    if streamer:
        if streamer == 'transmit':
            stream_transmitter = Transmitter(**kwargs)
            return stream_transmitter

        if streamer == 'worker':
            stream_worker = Worker(**kwargs)
            return stream_worker

        if streamer == 'process':
            stream_processor = Processor(event_handler=event_callback_handler,
                                         status_handler=status_callback_handler,
                                         artifacts_handler=artifacts_handler,
                                         cancel_callback=cancel_callback,
                                         finished_callback=finished_callback,
                                         **kwargs)
            return stream_processor

    kwargs.pop('_input', None)
    kwargs.pop('_output', None)
    rc = RunnerConfig(**kwargs)
    rc.prepare()

    return Runner(rc,
                  event_handler=event_callback_handler,
                  status_handler=status_callback_handler,
                  artifacts_handler=artifacts_handler,
                  cancel_callback=cancel_callback,
                  finished_callback=finished_callback)


def run(**kwargs):
    '''
    Run an Ansible Runner task in the foreground and return a Runner object when complete.

    :param private_data_dir: The directory containing all runner metadata needed to invoke the runner
                             module. Output artifacts will also be stored here for later consumption.
    :param ident: The run identifier for this invocation of Runner. Will be used to create and name
                  the artifact directory holding the results of the invocation.
    :param json_mode: Store event data in place of stdout on the console and in the stdout file
    :param playbook: The playbook (either supplied here as a list or string... or as a path relative to
                     ``private_data_dir/project``) that will be invoked by runner when executing Ansible.
    :param module: The module that will be invoked in ad-hoc mode by runner when executing Ansible.
    :param module_args: The module arguments that will be supplied to ad-hoc mode.
    :param host_pattern: The host pattern to match when running in ad-hoc mode.
    :param inventory: Overrides the inventory directory/file (supplied at ``private_data_dir/inventory``) with
                      a specific host or list of hosts. This can take the form of
      - Path to the inventory file in the ``private_data_dir``
      - Native python dict supporting the YAML/json inventory structure
      - A text INI formatted string
      - A list of inventory sources, or an empty list to disable passing inventory
    :param roles_path: Directory or list of directories to assign to ANSIBLE_ROLES_PATH
    :param envvars: Environment variables to be used when running Ansible. Environment variables will also be
                    read from ``env/envvars`` in ``private_data_dir``
    :param extravars: Extra variables to be passed to Ansible at runtime using ``-e``. Extra vars will also be
                      read from ``env/extravars`` in ``private_data_dir``.
    :param passwords: A dictionary containing password prompt patterns and response values used when processing output from
                      Ansible. Passwords will also be read from ``env/passwords`` in ``private_data_dir``.
    :param settings: A dictionary containing settings values for the ``ansible-runner`` runtime environment. These will also
                     be read from ``env/settings`` in ``private_data_dir``.
    :param ssh_key: The ssh private key passed to ``ssh-agent`` as part of the ansible-playbook run.
    :param cmdline: Command line options passed to Ansible read from ``env/cmdline`` in ``private_data_dir``
    :param limit: Matches ansible's ``--limit`` parameter to further constrain the inventory to be used
    :param forks: Control Ansible parallel concurrency
    :param verbosity: Control how verbose the output of ansible-playbook is
    :param quiet: Disable all output
    :param artifact_dir: The path to the directory where artifacts should live, this defaults to 'artifacts' under the private data dir
    :param project_dir: The path to the playbook content, this defaults to 'project' within the private data dir
    :param rotate_artifacts: Keep at most n artifact directories, disable with a value of 0 which is the default
    :param streamer: Optionally invoke ansible-runner as one of the steps in the streaming pipeline
    :param _input: An optional file or file-like object for use as input in a streaming pipeline
    :param _output: An optional file or file-like object for use as output in a streaming pipeline
    :param event_handler: An optional callback that will be invoked any time an event is received by Runner itself, return True to keep the event
    :param cancel_callback: An optional callback that can inform runner to cancel (returning True) or not (returning False)
    :param finished_callback: An optional callback that will be invoked at shutdown after process cleanup.
    :param status_handler: An optional callback that will be invoked any time the status changes (e.g...started, running, failed, successful, timeout)
    :param artifacts_handler: An optional callback that will be invoked at the end of the run to deal with the artifacts from the run.
    :param process_isolation: Enable process isolation, using either a container engine (e.g. podman) or a sandbox (e.g. bwrap).
    :param process_isolation_executable: Process isolation executable or container engine used to isolate execution. (default: podman)
    :param process_isolation_path: Path that an isolated playbook run will use for staging. (default: /tmp)
    :param process_isolation_hide_paths: A path or list of paths on the system that should be hidden from the playbook run.
    :param process_isolation_show_paths: A path or list of paths on the system that should be exposed to the playbook run.
    :param process_isolation_ro_paths: A path or list of paths on the system that should be exposed to the playbook run as read-only.
    :param container_image: Container image to use when running an ansible task (default: quay.io/ansible/ansible-runner:devel)
    :param container_volume_mounts: List of bind mounts in the form 'host_dir:/container_dir. (default: None)
    :param container_options: List of container options to pass to execution engine.
    :param resource_profiling: Enable collection of resource utilization data during playbook execution.
    :param resource_profiling_base_cgroup: Name of existing cgroup which will be sub-grouped in order to measure resource utilization (default: ansible-runner)
    :param resource_profiling_cpu_poll_interval: Interval (in seconds) between CPU polling for determining CPU usage (default: 0.25)
    :param resource_profiling_memory_poll_interval: Interval (in seconds) between memory polling for determining memory usage (default: 0.25)
    :param resource_profiling_pid_poll_interval: Interval (in seconds) between polling PID count for determining number of processes used (default: 0.25)
    :param resource_profiling_results_dir: Directory where profiling data files should be saved (defaults to profiling_data folder inside private data dir)
    :param directory_isolation_base_path: An optional path will be used as the base path to create a temp directory, the project contents will be
                                          copied to this location which will then be used as the working directory during playbook execution.
    :param fact_cache: A string that will be used as the name for the subdirectory of the fact cache in artifacts directory.
                       This is only used for 'jsonfile' type fact caches.
    :param fact_cache_type: A string of the type of fact cache to use.  Defaults to 'jsonfile'.
    :param omit_event_data: Omits extra ansible event data from event payload (stdout and event still included)
    :param only_failed_event_data: Omits extra ansible event data unless it's a failed event (stdout and event still included)
    :param cli_execenv_cmd: Tells Ansible Runner to emulate the CLI of Ansible by prepping an Execution Environment and then passing the user provided cmdline.
                            Allows executing a python script by passing the full executable path and aribary pass through commands.
    :param cli_execenv_cmd_cwd: Tells Ansible Runner the current local working directory for the command provided by ``cli_execenv_cmd``.
    :param cli_execenv_cmd_containter_workdir: Applicable only for command provided by ``cli_execenv_cmd`` parameter and running within a container.
                                               Tells Ansible Runner the work directory to use within container.
    :type private_data_dir: str
    :type ident: str
    :type json_mode: bool
    :type playbook: str or filename or list
    :type inventory: str or dict or list
    :type envvars: dict
    :type extravars: dict
    :type passwords: dict
    :type settings: dict
    :type ssh_key: str
    :type artifact_dir: str
    :type project_dir: str
    :type rotate_artifacts: int
    :type cmdline: str
    :type limit: str
    :type forks: int
    :type quiet: bool
    :type verbosity: int
    :type streamer: str
    :type _input: file
    :type _output: file
    :type event_handler: function
    :type cancel_callback: function
    :type finished_callback: function
    :type status_handler: function
    :type artifacts_handler: function
    :type process_isolation: bool
    :type process_isolation_executable: str
    :type process_isolation_path: str
    :type process_isolation_hide_paths: str or list
    :type process_isolation_show_paths: str or list
    :type process_isolation_ro_paths: str or list
    :type container_image: str
    :type container_volume_mounts: list
    :type container_options: list
    :type resource_profiling: bool
    :type resource_profiling_base_cgroup: str
    :type resource_profiling_cpu_poll_interval: float
    :type resource_profiling_memory_poll_interval: float
    :type resource_profiling_pid_poll_interval: float
    :type resource_profiling_results_dir: str
    :type directory_isolation_base_path: str
    :type fact_cache: str
    :type fact_cache_type: str
    :type omit_event_data: bool
    :type only_failed_event_data: bool
    :type cli_execenv_cmd: str
    :type cli_execenv_cmd_cwd: str
    : type cli_execenv_cmd_containter_workdir: str

    :returns: A :py:class:`ansible_runner.runner.Runner` object, or a simple object containing `rc` if run remotely
    '''
    r = init_runner(**kwargs)
    r.run()
    return r


def run_async(**kwargs):
    '''
    Runs an Ansible Runner task in the background which will start immediately. Returns the thread object and a Runner object.

    This uses the same parameters as :py:func:`ansible_runner.interface.run`

    :returns: A tuple containing a :py:class:`threading.Thread` object and a :py:class:`ansible_runner.runner.Runner` object
    '''
    r = init_runner(**kwargs)
    runner_thread = threading.Thread(target=r.run)
    runner_thread.start()
    return runner_thread, r
