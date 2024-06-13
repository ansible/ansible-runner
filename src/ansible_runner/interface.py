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
import json
import sys
import threading
import logging

from ansible_runner import output
from ansible_runner.config.runner import RunnerConfig
from ansible_runner.config.command import CommandConfig
from ansible_runner.config.inventory import InventoryConfig
from ansible_runner.config.ansible_cfg import AnsibleCfgConfig
from ansible_runner.config.doc import DocConfig
from ansible_runner.runner import Runner
from ansible_runner.streaming import Transmitter, Worker, Processor
from ansible_runner.utils import (
    dump_artifacts,
    check_isolation_executable_installed,
    sanitize_json_response,
    signal_handler,
)

logging.getLogger('ansible-runner').addHandler(logging.NullHandler())


def init_runner(**kwargs):
    '''
    Initialize the Runner() instance

    This function will properly initialize both run() and run_async()
    functions in the same way and return a value instance of Runner.

    See parameters given to :py:func:`ansible_runner.interface.run`
    '''

    # Handle logging first thing
    debug = kwargs.pop('debug', None)
    logfile = kwargs.pop('logfile', None)

    if not kwargs.pop("ignore_logging", True):
        output.configure()
        if debug in (True, False):
            output.set_debug('enable' if debug is True else 'disable')

        if logfile:
            output.set_logfile(logfile)

    # If running via the transmit-worker-process method, we must only extract things as read-only
    # inside of one of these commands. That could be either transmit or worker.
    if kwargs.get('streamer') not in ('worker', 'process'):
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

    event_callback_handler = kwargs.pop('event_handler', None)
    status_callback_handler = kwargs.pop('status_handler', None)
    artifacts_handler = kwargs.pop('artifacts_handler', None)
    cancel_callback = kwargs.pop('cancel_callback', None)
    if cancel_callback is None:
        # attempt to load signal handler.
        # will return None if we are not in the main thread
        cancel_callback = signal_handler()
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

    if kwargs.get("process_isolation", False):
        pi_executable = kwargs.get("process_isolation_executable", "podman")
        if not check_isolation_executable_installed(pi_executable):
            print(f'Unable to find process isolation executable: {pi_executable}')
            sys.exit(1)

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

    :param str private_data_dir: The directory containing all runner metadata needed to invoke the runner
                             module. Output artifacts will also be stored here for later consumption.
    :param str ident: The run identifier for this invocation of Runner. Will be used to create and name
                  the artifact directory holding the results of the invocation.
    :param bool json_mode: Store event data in place of stdout on the console and in the stdout file
    :param str or list playbook: The playbook (either a list or dictionary of plays, or as a path relative to
                     ``private_data_dir/project``) that will be invoked by runner when executing Ansible.
    :param str module: The module that will be invoked in ad-hoc mode by runner when executing Ansible.
    :param str module_args: The module arguments that will be supplied to ad-hoc mode.
    :param str host_pattern: The host pattern to match when running in ad-hoc mode.
    :param str or dict or list inventory: Overrides the inventory directory/file (supplied at ``private_data_dir/inventory``) with
        a specific host or list of hosts. This can take the form of:

            - Path to the inventory file in the ``private_data_dir/inventory`` directory or
              an absolute path to the inventory file
            - Native python dict supporting the YAML/json inventory structure
            - A text INI formatted string
            - A list of inventory sources, or an empty list to disable passing inventory

    :param str role: Name of the role to execute.
    :param str or list roles_path: Directory or list of directories to assign to ANSIBLE_ROLES_PATH
    :param dict envvars: Environment variables to be used when running Ansible. Environment variables will also be
                    read from ``env/envvars`` in ``private_data_dir``
    :param dict extravars: Extra variables to be passed to Ansible at runtime using ``-e``. Extra vars will also be
                      read from ``env/extravars`` in ``private_data_dir``.
    :param dict passwords: A dictionary containing password prompt patterns and response values used when processing output from
                      Ansible. Passwords will also be read from ``env/passwords`` in ``private_data_dir``.
    :param dict settings: A dictionary containing settings values for the ``ansible-runner`` runtime environment. These will also
                     be read from ``env/settings`` in ``private_data_dir``.
    :param str ssh_key: The ssh private key passed to ``ssh-agent`` as part of the ansible-playbook run.
    :param str cmdline: Command line options passed to Ansible read from ``env/cmdline`` in ``private_data_dir``
    :param bool suppress_env_files: Disable the writing of files into the ``env`` which may store sensitive information
    :param str limit: Matches ansible's ``--limit`` parameter to further constrain the inventory to be used
    :param int forks: Control Ansible parallel concurrency
    :param int verbosity: Control how verbose the output of ansible-playbook is
    :param bool quiet: Disable all output
    :param str artifact_dir: The path to the directory where artifacts should live, this defaults to 'artifacts' under the private data dir
    :param str project_dir: The path to the playbook content, this defaults to 'project' within the private data dir
    :param int rotate_artifacts: Keep at most n artifact directories, disable with a value of 0 which is the default
    :param int timeout: The timeout value in seconds that will be passed to either ``pexpect`` of ``subprocess`` invocation
                    (based on ``runner_mode`` selected) while executing command. It the timeout is triggered it will force cancel the
                    execution.
    :param str streamer: Optionally invoke ansible-runner as one of the steps in the streaming pipeline
    :param io.FileIO _input: An optional file or file-like object for use as input in a streaming pipeline
    :param io.FileIO _output: An optional file or file-like object for use as output in a streaming pipeline
    :param Callable event_handler: An optional callback that will be invoked any time an event is received by Runner itself, return True to keep the event
    :param Callable cancel_callback: An optional callback that can inform runner to cancel (returning True) or not (returning False)
    :param Callable finished_callback: An optional callback that will be invoked at shutdown after process cleanup.
    :param Callable status_handler: An optional callback that will be invoked any time the status changes (e.g...started, running, failed, successful, timeout)
    :param Callable artifacts_handler: An optional callback that will be invoked at the end of the run to deal with the artifacts from the run.
    :param bool process_isolation: Enable process isolation, using either a container engine (e.g. podman) or a sandbox (e.g. bwrap).
    :param str process_isolation_executable: Process isolation executable or container engine used to isolate execution. (default: podman)
    :param str process_isolation_path: Path that an isolated playbook run will use for staging. (default: /tmp)
    :param str or list process_isolation_hide_paths: A path or list of paths on the system that should be hidden from the playbook run.
    :param str or list process_isolation_show_paths: A path or list of paths on the system that should be exposed to the playbook run.
    :param str or list process_isolation_ro_paths: A path or list of paths on the system that should be exposed to the playbook run as read-only.
    :param str container_image: Container image to use when running an ansible task
    :param list container_volume_mounts: List of bind mounts in the form 'host_dir:/container_dir. (default: None)
    :param list container_options: List of container options to pass to execution engine.
    :param str directory_isolation_base_path: An optional path will be used as the base path to create a temp directory, the project contents will be
                                          copied to this location which will then be used as the working directory during playbook execution.
    :param str fact_cache: A string that will be used as the name for the subdirectory of the fact cache in artifacts directory.
                       This is only used for 'jsonfile' type fact caches.
    :param str fact_cache_type: A string of the type of fact cache to use.  Defaults to 'jsonfile'.
    :param bool omit_event_data: Omits extra ansible event data from event payload (stdout and event still included)
    :param bool only_failed_event_data: Omits extra ansible event data unless it's a failed event (stdout and event still included)
    :param bool check_job_event_data: Check if job events data is completely generated. If event data is not completely generated and if
                                 value is set to 'True' it will raise 'AnsibleRunnerException' exception,
                                 if set to 'False' it log a debug message and continue execution. Default value is 'False'

    :returns: A :py:class:`ansible_runner.runner.Runner` object, or a simple object containing ``rc`` if run remotely
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


def init_command_config(executable_cmd, cmdline_args=None, **kwargs):
    '''
    Initialize the Runner() instance

    This function will properly initialize both run_command() and run_command_async()
    functions in the same way and return a value instance of Runner.

    See parameters given to :py:func:`ansible_runner.interface.run_command`
    '''
    event_callback_handler = kwargs.pop('event_handler', None)
    status_callback_handler = kwargs.pop('status_handler', None)
    artifacts_handler = kwargs.pop('artifacts_handler', None)
    cancel_callback = kwargs.pop('cancel_callback', None)
    finished_callback = kwargs.pop('finished_callback', None)

    rc = CommandConfig(**kwargs)
    rc.prepare_run_command(executable_cmd, cmdline_args=cmdline_args)
    return Runner(rc,
                  event_handler=event_callback_handler,
                  status_handler=status_callback_handler,
                  artifacts_handler=artifacts_handler,
                  cancel_callback=cancel_callback,
                  finished_callback=finished_callback)


def run_command(executable_cmd, cmdline_args=None, **kwargs):
    '''
    Run an (Ansible) commands in the foreground and return a Runner object when complete.

    :param str executable_cmd: The command to be executed.
    :param list cmdline_args: A list of arguments to be passed to the executable command.
    :param int input_fd: This parameter is applicable when ``runner_mode`` is set to ``subprocess``, it provides the
                     input file descrption to interact with the sub-process running the command.
    :param int output_fd: The output file descriptor to stream the output of command execution.
    :param int error_fd: This parameter is applicable when ``runner_mode`` is set to ``subprocess``, it provides the
                     error file descrption to read the error received while executing the command.
    :param str runner_mode: The applicable values are ``pexpect`` and ``subprocess``. If the value of ``input_fd`` parameter
                        is set or the executable command is one of ``ansible-config``, ``ansible-doc`` or ``ansible-galaxy``
                        the default value is set to ``subprocess`` else in other cases it is set to ``pexpect``.
    :param str host_cwd: The host current working directory to be mounted within the container (if enabled) and will be
                     the work directory within container.
    :param dict envvars: Environment variables to be used when running Ansible. Environment variables will also be
                    read from ``env/envvars`` in ``private_data_dir``
    :param dict passwords: A dictionary containing password prompt patterns and response values used when processing output from
                      Ansible. Passwords will also be read from ``env/passwords`` in ``private_data_dir``.
    :param dict settings: A dictionary containing settings values for the ``ansible-runner`` runtime environment. These will also
                     be read from ``env/settings`` in ``private_data_dir``.
    :param str ssh_key: The ssh private key passed to ``ssh-agent`` as part of the ansible-playbook run.
    :param bool quiet: Disable all output
    :param bool json_mode: Store event data in place of stdout on the console and in the stdout file
    :param str artifact_dir: The path to the directory where artifacts should live, this defaults to 'artifacts' under the private data dir
    :param str project_dir: The path to the playbook content, this defaults to 'project' within the private data dir
    :param int rotate_artifacts: Keep at most n artifact directories, disable with a value of 0 which is the default
    :param int timeout: The timeout value in seconds that will be passed to either ``pexpect`` of ``subprocess`` invocation
                    (based on ``runner_mode`` selected) while executing command. It the timeout is triggered it will force cancel the
                    execution.
    :param bool process_isolation: Enable process isolation, using a container engine (e.g. podman).
    :param str process_isolation_executable: Process isolation executable or container engine used to isolate execution. (default: podman)
    :param str container_image: Container image to use when running an ansible task
    :param list container_volume_mounts: List of bind mounts in the form 'host_dir:/container_dir:labels. (default: None)
    :param list container_options: List of container options to pass to execution engine.
    :param str container_workdir: The working directory within the container.
    :param str fact_cache: A string that will be used as the name for the subdirectory of the fact cache in artifacts directory.
                       This is only used for 'jsonfile' type fact caches.
    :param str fact_cache_type: A string of the type of fact cache to use.  Defaults to 'jsonfile'.
    :param str private_data_dir: The directory containing all runner metadata needed to invoke the runner
                             module. Output artifacts will also be stored here for later consumption.
    :param str ident: The run identifier for this invocation of Runner. Will be used to create and name
                  the artifact directory holding the results of the invocation.
    :param Callable event_handler: An optional callback that will be invoked any time an event is received by Runner itself, return True to keep the event
    :param Callable cancel_callback: An optional callback that can inform runner to cancel (returning True) or not (returning False)
    :param Callable finished_callback: An optional callback that will be invoked at shutdown after process cleanup.
    :param Callable status_handler: An optional callback that will be invoked any time the status changes (e.g...started, running, failed, successful, timeout)
    :param Callable artifacts_handler: An optional callback that will be invoked at the end of the run to deal with the artifacts from the run.
    :param bool check_job_event_data: Check if job events data is completely generated. If event data is not completely generated and if
                                 value is set to 'True' it will raise 'AnsibleRunnerException' exception,
                                 if set to 'False' it log a debug message and continue execution. Default value is 'False'

    :returns: Returns a tuple of response, error string and return code.
              In case if ``runner_mode`` is set to ``pexpect`` the error value is empty as
              ``pexpect`` uses same output descriptor for stdout and stderr.
    '''
    r = init_command_config(executable_cmd, cmdline_args=cmdline_args, **kwargs)
    r.run()
    with r.stdout as stdout, r.stderr as stderr:
        response = stdout.read()
        error = stderr.read()
    return response, error, r.rc


def run_command_async(executable_cmd, cmdline_args=None, **kwargs):
    '''
    Run an (Ansible) commands in the background which will start immediately. Returns the thread object and a Runner object.

    This uses the same parameters as :py:func:`ansible_runner.interface.run_command`

    :returns: A tuple containing a :py:class:`threading.Thread` object and a :py:class:`ansible_runner.runner.Runner` object
    '''
    r = init_command_config(executable_cmd, cmdline_args=cmdline_args, **kwargs)
    runner_thread = threading.Thread(target=r.run)
    runner_thread.start()
    return runner_thread, r


def init_plugin_docs_config(plugin_names, plugin_type=None, response_format=None,
                            snippet=False, playbook_dir=None, module_path=None, **kwargs):
    '''
    Initialize the Runner() instance

    This function will properly initialize both get_plugin_docs() and get_plugin_docs_async()
    functions in the same way and return a value instance of Runner.

    See parameters given to :py:func:`ansible_runner.interface.get_plugin_docs`
    '''

    event_callback_handler = kwargs.pop('event_handler', None)
    status_callback_handler = kwargs.pop('status_handler', None)
    artifacts_handler = kwargs.pop('artifacts_handler', None)
    cancel_callback = kwargs.pop('cancel_callback', None)
    finished_callback = kwargs.pop('finished_callback', None)

    rd = DocConfig(**kwargs)
    rd.prepare_plugin_docs_command(plugin_names, plugin_type=plugin_type, response_format=response_format,
                                   snippet=snippet, playbook_dir=playbook_dir, module_path=module_path)
    return Runner(rd, event_handler=event_callback_handler, status_handler=status_callback_handler, artifacts_handler=artifacts_handler,
                  cancel_callback=cancel_callback, finished_callback=finished_callback)


def get_plugin_docs(plugin_names, plugin_type=None, response_format=None, snippet=False, playbook_dir=None, module_path=None, **kwargs):
    '''
    Run an ansible-doc command to get plugin docs  in the foreground and return a Runner object when complete.

    :param plugin_names: The name of the plugins to get docs.
    :param plugin_type: The type of the plugin mentioned in plugins_names. Valid values are ``become``, ``cache``, ``callback``,
                        ``cliconf``, ``connection``, ``httpapi``, ``inventory``, ``lookup``, ``netconf``, ``shell``, ``vars``,
                        ``module``, ``strategy``. If the value is not provided it defaults to ``module``.
    :param response_format: The output format for response. Valid values can be one of ``json`` or ``human`` and the response
                            is either json string or plain text in human readable foramt. Default value is ``json``.
    :param snippet: Show playbook snippet for specified plugin(s).
    :param playbook_dir: This parameter is used to sets the relative path to handle playbook adjacent installed plugins.
    :param module_path: This parameter is prepend colon-separated path(s) to module library
                        (default=~/.ansible/plugins/modules:/usr/share/ansible/plugins/modules).
    :param runner_mode: The applicable values are ``pexpect`` and ``subprocess``. Default is set to ``subprocess``.
    :param host_cwd: The host current working directory to be mounted within the container (if enabled) and will be
                     the work directory within container.
    :param envvars: Environment variables to be used when running Ansible. Environment variables will also be
                    read from ``env/envvars`` in ``private_data_dir``
    :param passwords: A dictionary containing password prompt patterns and response values used when processing output from
                      Ansible. Passwords will also be read from ``env/passwords`` in ``private_data_dir``.
    :param settings: A dictionary containing settings values for the ``ansible-runner`` runtime environment. These will also
                     be read from ``env/settings`` in ``private_data_dir``.
    :param ssh_key: The ssh private key passed to ``ssh-agent`` as part of the ansible-playbook run.
    :param quiet: Disable all output
    :param json_mode: Store event data in place of stdout on the console and in the stdout file
    :param artifact_dir: The path to the directory where artifacts should live, this defaults to 'artifacts' under the private data dir
    :param project_dir: The path to the playbook content, this defaults to 'project' within the private data dir
    :param rotate_artifacts: Keep at most n artifact directories, disable with a value of 0 which is the default
    :param timeout: The timeout value in seconds that will be passed to either ``pexpect`` of ``subprocess`` invocation
                    (based on ``runner_mode`` selected) while executing command. It the timeout is triggered it will force cancel the
                    execution.
    :param process_isolation: Enable process isolation, using a container engine (e.g. podman).
    :param process_isolation_executable: Process isolation executable or container engine used to isolate execution. (default: podman)
    :param container_image: Container image to use when running an ansible task
    :param container_volume_mounts: List of bind mounts in the form 'host_dir:/container_dir:labels. (default: None)
    :param container_options: List of container options to pass to execution engine.
    :param container_workdir: The working directory within the container.
    :param fact_cache: A string that will be used as the name for the subdirectory of the fact cache in artifacts directory.
                       This is only used for 'jsonfile' type fact caches.
    :param fact_cache_type: A string of the type of fact cache to use.  Defaults to 'jsonfile'.
    :param private_data_dir: The directory containing all runner metadata needed to invoke the runner
                             module. Output artifacts will also be stored here for later consumption.
    :param ident: The run identifier for this invocation of Runner. Will be used to create and name
                  the artifact directory holding the results of the invocation.
    :param event_handler: An optional callback that will be invoked any time an event is received by Runner itself, return True to keep the event
    :param cancel_callback: An optional callback that can inform runner to cancel (returning True) or not (returning False)
    :param finished_callback: An optional callback that will be invoked at shutdown after process cleanup.
    :param status_handler: An optional callback that will be invoked any time the status changes (e.g...started, running, failed, successful, timeout)
    :param artifacts_handler: An optional callback that will be invoked at the end of the run to deal with the artifacts from the run.
    :param check_job_event_data: Check if job events data is completely generated. If event data is not completely generated and if
                                 value is set to 'True' it will raise 'AnsibleRunnerException' exception,
                                 if set to 'False' it log a debug message and continue execution. Default value is 'False'

    :type plugin_names: list
    :type plugin_type: str
    :type response_format: str
    :type snippet: bool
    :type playbook_dir: str
    :type module_path: str
    :type runner_mode: str
    :type host_cwd: str
    :type envvars: dict
    :type passwords: dict
    :type settings: dict
    :type private_data_dir: str
    :type project_dir: str
    :type artifact_dir: str
    :type fact_cache_type: str
    :type fact_cache: str
    :type process_isolation: bool
    :type process_isolation_executable: str
    :type container_image: str
    :type container_volume_mounts: list
    :type container_options: list
    :type container_workdir: str
    :type ident: str
    :type rotate_artifacts: int
    :type timeout: int
    :type ssh_key: str
    :type quiet: bool
    :type json_mode: bool
    :type event_handler: Callable
    :type cancel_callback: Callable
    :type finished_callback: Callable
    :type status_handler: Callable
    :type artifacts_handler: Callable
    :type check_job_event_data: bool

    :returns: Returns a tuple of response and error string. In case if ``runner_mode`` is set to ``pexpect`` the error value is empty as
              ``pexpect`` uses same output descriptor for stdout and stderr. If the value of ``response_format`` is ``json``
              it returns a python dictionary object.
    '''
    r = init_plugin_docs_config(plugin_names, plugin_type=plugin_type, response_format=response_format,
                                snippet=snippet, playbook_dir=playbook_dir, module_path=module_path, **kwargs)
    r.run()
    with r.stdout as stdout, r.stderr as stderr:
        response = stdout.read()
        error = stderr.read()
    if response and response_format == 'json':
        response = json.loads(sanitize_json_response(response))
    return response, error


def get_plugin_docs_async(plugin_names, plugin_type=None, response_format=None, snippet=False, playbook_dir=None, module_path=None, **kwargs):
    '''
    Run an ansible-doc command in the background which will start immediately. Returns the thread object and a Runner object.

    This uses the same parameters as :py:func:`ansible_runner.interface.get_plugin_docs`

    :returns: A tuple containing a :py:class:`threading.Thread` object and a :py:class:`ansible_runner.runner.Runner` object
    '''
    r = init_plugin_docs_config(plugin_names, plugin_type=plugin_type, response_format=response_format,
                                snippet=snippet, playbook_dir=playbook_dir, module_path=module_path, **kwargs)
    doc_runner_thread = threading.Thread(target=r.run)
    doc_runner_thread.start()
    return doc_runner_thread, r


def get_plugin_list(list_files=None, response_format=None, plugin_type=None, playbook_dir=None, module_path=None, **kwargs):
    '''
    Run an ansible-doc command to get list of installed Ansible plugins.

    :param list_files: The boolean parameter is set to ``True`` returns file path of the plugin along with the plugin name.
    :param response_format: The output format for response. Valid values can be one of ``json`` or ``human`` and the response
                            is either json string or plain text in human readable foramt. Default value is ``json``.
    :param plugin_type: The type of the plugin mentioned in plugins_names. Valid values are ``become``, ``cache``, ``callback``,
                        ``cliconf``, ``connection``, ``httpapi``, ``inventory``, ``lookup``, ``netconf``, ``shell``, ``vars``,
                        ``module``, ``strategy``. If the value is not provided it defaults to ``module``.
    :param playbook_dir: This parameter is used to sets the relative path to handle playbook adjacent installed plugins.
    :param module_path: This parameter is prepend colon-separated path(s) to module library
                        (default=~/.ansible/plugins/modules:/usr/share/ansible/plugins/modules).
    :param runner_mode: The applicable values are ``pexpect`` and ``subprocess``. Default is set to ``subprocess``.
    :param host_cwd: The host current working directory to be mounted within the container (if enabled) and will be
                     the work directory within container.
    :param envvars: Environment variables to be used when running Ansible. Environment variables will also be
                    read from ``env/envvars`` in ``private_data_dir``
    :param passwords: A dictionary containing password prompt patterns and response values used when processing output from
                      Ansible. Passwords will also be read from ``env/passwords`` in ``private_data_dir``.
    :param settings: A dictionary containing settings values for the ``ansible-runner`` runtime environment. These will also
                     be read from ``env/settings`` in ``private_data_dir``.
    :param ssh_key: The ssh private key passed to ``ssh-agent`` as part of the ansible-playbook run.
    :param quiet: Disable all output
    :param json_mode: Store event data in place of stdout on the console and in the stdout file
    :param artifact_dir: The path to the directory where artifacts should live, this defaults to 'artifacts' under the private data dir
    :param project_dir: The path to the playbook content, this defaults to 'project' within the private data dir
    :param rotate_artifacts: Keep at most n artifact directories, disable with a value of 0 which is the default
    :param timeout: The timeout value in seconds that will be passed to either ``pexpect`` of ``subprocess`` invocation
                    (based on ``runner_mode`` selected) while executing command. It the timeout is triggered it will force cancel the
                    execution.
    :param process_isolation: Enable process isolation, using a container engine (e.g. podman).
    :param process_isolation_executable: Process isolation executable or container engine used to isolate execution. (default: podman)
    :param container_image: Container image to use when running an ansible task
    :param container_volume_mounts: List of bind mounts in the form 'host_dir:/container_dir:labels. (default: None)
    :param container_options: List of container options to pass to execution engine.
    :param container_workdir: The working directory within the container.
    :param fact_cache: A string that will be used as the name for the subdirectory of the fact cache in artifacts directory.
                       This is only used for 'jsonfile' type fact caches.
    :param fact_cache_type: A string of the type of fact cache to use.  Defaults to 'jsonfile'.
    :param private_data_dir: The directory containing all runner metadata needed to invoke the runner
                             module. Output artifacts will also be stored here for later consumption.
    :param ident: The run identifier for this invocation of Runner. Will be used to create and name
                  the artifact directory holding the results of the invocation.
    :param event_handler: An optional callback that will be invoked any time an event is received by Runner itself, return True to keep the event
    :param cancel_callback: An optional callback that can inform runner to cancel (returning True) or not (returning False)
    :param finished_callback: An optional callback that will be invoked at shutdown after process cleanup.
    :param status_handler: An optional callback that will be invoked any time the status changes (e.g...started, running, failed, successful, timeout)
    :param artifacts_handler: An optional callback that will be invoked at the end of the run to deal with the artifacts from the run.
    :param check_job_event_data: Check if job events data is completely generated. If event data is not completely generated and if
                                 value is set to 'True' it will raise 'AnsibleRunnerException' exception,
                                 if set to 'False' it log a debug message and continue execution. Default value is 'False'

    :type list_files: bool
    :type plugin_type: str
    :type response_format: str
    :type playbook_dir: str
    :type module_path: str
    :type runner_mode: str
    :type host_cwd: str
    :type envvars: dict
    :type passwords: dict
    :type settings: dict
    :type private_data_dir: str
    :type project_dir: str
    :type artifact_dir: str
    :type fact_cache_type: str
    :type fact_cache: str
    :type process_isolation: bool
    :type process_isolation_executable: str
    :type container_image: str
    :type container_volume_mounts: list
    :type container_options: list
    :type container_workdir: str
    :type ident: str
    :type rotate_artifacts: int
    :type timeout: int
    :type ssh_key: str
    :type quiet: bool
    :type json_mode: bool
    :type event_handler: Callable
    :type cancel_callback: Callable
    :type finished_callback: Callable
    :type status_handler: Callable
    :type artifacts_handler: Callable
    :type check_job_event_data: bool

    :returns: Returns a tuple of response and error string. In case if ``runner_mode`` is set to ``pexpect`` the error value is empty as
              ``pexpect`` uses same output descriptor for stdout and stderr. If the value of ``response_format`` is ``json``
              it returns a python dictionary object.
    '''
    event_callback_handler = kwargs.pop('event_handler', None)
    status_callback_handler = kwargs.pop('status_handler', None)
    artifacts_handler = kwargs.pop('artifacts_handler', None)
    cancel_callback = kwargs.pop('cancel_callback', None)
    finished_callback = kwargs.pop('finished_callback', None)

    rd = DocConfig(**kwargs)
    rd.prepare_plugin_list_command(list_files=list_files, response_format=response_format, plugin_type=plugin_type,
                                   playbook_dir=playbook_dir, module_path=module_path)
    r = Runner(rd,
               event_handler=event_callback_handler,
               status_handler=status_callback_handler,
               artifacts_handler=artifacts_handler,
               cancel_callback=cancel_callback,
               finished_callback=finished_callback)
    r.run()
    with r.stdout as stdout, r.stderr as stderr:
        response = stdout.read()
        error = stderr.read()
    if response and response_format == 'json':
        response = json.loads(sanitize_json_response(response))
    return response, error


def get_inventory(action, inventories, response_format=None, host=None, playbook_dir=None,
                  vault_ids=None, vault_password_file=None, output_file=None, export=None, **kwargs):
    '''
    Run an ansible-inventory command to get inventory related details.

    :param action: Valid values are one of ``graph``, ``host``, ``list``.
                   ``graph`` returns the inventory graph.
                   ``host`` returns info for a specific host and works as an inventory script.
                   ``list`` returns info for all hosts and also works as an inventory script.
    :param inventories: List of inventory host path.
    :param response_format: The output format for response. Valid values can be one of ``json``, ``yaml``, ``toml``.
                            Default is ``json``. If ``action`` is ``graph`` only allowed value is ``json``.
    :param host: When ``action`` is set to ``host`` this parameter is used to get the host specific information.
    :param playbook_dir: This parameter is used to sets the relative path for the inventory.
    :param vault_ids: The vault identity to use.
    :param vault_password_file: The vault password files to use.
    :param output_file: The file path in which inventory details should be sent to.
    :param export: The boolean value if set represent in a way that is optimized for export,not as an accurate
                   representation of how Ansible has processed it.
    :param runner_mode: The applicable values are ``pexpect`` and ``subprocess``. Default is set to ``subprocess``.
    :param host_cwd: The host current working directory to be mounted within the container (if enabled) and will be
                     the work directory within container.
    :param envvars: Environment variables to be used when running Ansible. Environment variables will also be
                    read from ``env/envvars`` in ``private_data_dir``
    :param passwords: A dictionary containing password prompt patterns and response values used when processing output from
                      Ansible. Passwords will also be read from ``env/passwords`` in ``private_data_dir``.
    :param settings: A dictionary containing settings values for the ``ansible-runner`` runtime environment. These will also
                     be read from ``env/settings`` in ``private_data_dir``.
    :param ssh_key: The ssh private key passed to ``ssh-agent`` as part of the ansible-playbook run.
    :param quiet: Disable all output
    :param json_mode: Store event data in place of stdout on the console and in the stdout file
    :param artifact_dir: The path to the directory where artifacts should live, this defaults to 'artifacts' under the private data dir
    :param project_dir: The path to the playbook content, this defaults to 'project' within the private data dir
    :param rotate_artifacts: Keep at most n artifact directories, disable with a value of 0 which is the default
    :param timeout: The timeout value in seconds that will be passed to either ``pexpect`` of ``subprocess`` invocation
                    (based on ``runner_mode`` selected) while executing command. It the timeout is triggered it will force cancel the
                    execution.
    :param process_isolation: Enable process isolation, using a container engine (e.g. podman).
    :param process_isolation_executable: Process isolation executable or container engine used to isolate execution. (default: podman)
    :param container_image: Container image to use when running an ansible task
    :param container_volume_mounts: List of bind mounts in the form 'host_dir:/container_dir:labels. (default: None)
    :param container_options: List of container options to pass to execution engine.
    :param container_workdir: The working directory within the container.
    :param fact_cache: A string that will be used as the name for the subdirectory of the fact cache in artifacts directory.
                       This is only used for 'jsonfile' type fact caches.
    :param fact_cache_type: A string of the type of fact cache to use.  Defaults to 'jsonfile'.
    :param private_data_dir: The directory containing all runner metadata needed to invoke the runner
                             module. Output artifacts will also be stored here for later consumption.
    :param ident: The run identifier for this invocation of Runner. Will be used to create and name
                  the artifact directory holding the results of the invocation.
    :param event_handler: An optional callback that will be invoked any time an event is received by Runner itself, return True to keep the event
    :param cancel_callback: An optional callback that can inform runner to cancel (returning True) or not (returning False)
    :param finished_callback: An optional callback that will be invoked at shutdown after process cleanup.
    :param status_handler: An optional callback that will be invoked any time the status changes (e.g...started, running, failed, successful, timeout)
    :param artifacts_handler: An optional callback that will be invoked at the end of the run to deal with the artifacts from the run.
    :param check_job_event_data: Check if job events data is completely generated. If event data is not completely generated and if
                                 value is set to 'True' it will raise 'AnsibleRunnerException' exception,
                                 if set to 'False' it log a debug message and continue execution. Default value is 'False'
    :type action: str
    :type inventories: list
    :type response_format: str
    :type host: str
    :type playbook_dir: str
    :type vault_ids: str
    :type vault_password_file: str
    :type output_file: str
    :type export: bool
    :type runner_mode: str
    :type host_cwd: str
    :type envvars: dict
    :type passwords: dict
    :type settings: dict
    :type private_data_dir: str
    :type project_dir: str
    :type artifact_dir: str
    :type fact_cache_type: str
    :type fact_cache: str
    :type process_isolation: bool
    :type process_isolation_executable: str
    :type container_image: str
    :type container_volume_mounts: list
    :type container_options: list
    :type container_workdir: str
    :type ident: str
    :type rotate_artifacts: int
    :type timeout: int
    :type ssh_key: str
    :type quiet: bool
    :type json_mode: bool
    :type event_handler: Callable
    :type cancel_callback: Callable
    :type finished_callback: Callable
    :type status_handler: Callable
    :type artifacts_handler: Callable
    :type check_job_event_data: bool

    :returns: Returns a tuple of response and error string. In case if ``runner_mode`` is set to ``pexpect`` the error value is
              empty as ``pexpect`` uses same output descriptor for stdout and stderr. If the vaue of ``response_format`` is ``json``
              it returns a python dictionary object.
    '''

    event_callback_handler = kwargs.pop('event_handler', None)
    status_callback_handler = kwargs.pop('status_handler', None)
    artifacts_handler = kwargs.pop('artifacts_handler', None)
    cancel_callback = kwargs.pop('cancel_callback', None)
    finished_callback = kwargs.pop('finished_callback', None)

    rd = InventoryConfig(**kwargs)
    rd.prepare_inventory_command(action=action, inventories=inventories, response_format=response_format, host=host, playbook_dir=playbook_dir,
                                 vault_ids=vault_ids, vault_password_file=vault_password_file, output_file=output_file, export=export)
    r = Runner(rd,
               event_handler=event_callback_handler,
               status_handler=status_callback_handler,
               artifacts_handler=artifacts_handler,
               cancel_callback=cancel_callback,
               finished_callback=finished_callback)
    r.run()
    with r.stdout as stdout, r.stderr as stderr:
        response = stdout.read()
        error = stderr.read()
    if response and response_format == 'json':
        response = json.loads(sanitize_json_response(response))
    return response, error


def get_ansible_config(action, config_file=None, only_changed=None, **kwargs):
    '''
    Run an ansible-config command to get ansible configuration releated details.

    :param action: Valid values are one of ``list``, ``dump``, ``view``
                   ``list`` returns all config options, ``dump`` returns the active configuration and
                   ``view`` returns the view of configuration file.
    :param config_file: Path to configuration file, defaults to first file found in precedence.                         .
    :param only_changed: The boolean value when set to ``True`` returns only the configurations that have changed
                         from the default. This parameter is applicable only when ``action`` is set to ``dump``.
    :param runner_mode: The applicable values are ``pexpect`` and ``subprocess``. Default is set to ``subprocess``.
    :param host_cwd: The current working directory from which the command in executable_cmd should be be executed.
    :param envvars: Environment variables to be used when running Ansible. Environment variables will also be
                    read from ``env/envvars`` in ``private_data_dir``
    :param passwords: A dictionary containing password prompt patterns and response values used when processing output from Ansible.
                      Passwords will also be read from ``env/passwords`` in ``private_data_dir``.
    :param settings: A dictionary containing settings values for the ``ansible-runner`` runtime environment. These will also
                     be read from ``env/settings`` in ``private_data_dir``.
    :param ssh_key: The ssh private key passed to ``ssh-agent`` as part of the ansible-playbook run.
    :param quiet: Disable all output
    :param json_mode: Store event data in place of stdout on the console and in the stdout file
    :param artifact_dir: The path to the directory where artifacts should live, this defaults to 'artifacts' under the private data dir
    :param project_dir: The path to the playbook content, this defaults to 'project' within the private data dir
    :param rotate_artifacts: Keep at most n artifact directories, disable with a value of 0 which is the default
    :param timeout: The timeout value in seconds that will be passed to either ``pexpect`` of ``subprocess`` invocation
                    (based on ``runner_mode`` selected) while executing command. It the timeout is triggered it will force cancel the
                    execution.
    :param process_isolation: Enable process isolation, using a container engine (e.g. podman).
    :param process_isolation_executable: Process isolation executable or container engine used to isolate execution. (default: podman)
    :param container_image: Container image to use when running an ansible task
    :param container_volume_mounts: List of bind mounts in the form 'host_dir:/container_dir:labels. (default: None)
    :param container_options: List of container options to pass to execution engine.
    :param container_workdir: The working directory within the container.
    :param fact_cache: A string that will be used as the name for the subdirectory of the fact cache in artifacts directory.
                       This is only used for 'jsonfile' type fact caches.
    :param fact_cache_type: A string of the type of fact cache to use.  Defaults to 'jsonfile'.
    :param private_data_dir: The directory containing all runner metadata needed to invoke the runner
                             module. Output artifacts will also be stored here for later consumption.
    :param ident: The run identifier for this invocation of Runner. Will be used to create and name
                  the artifact directory holding the results of the invocation.
    :param event_handler: An optional callback that will be invoked any time an event is received by Runner itself, return True to keep the event
    :param cancel_callback: An optional callback that can inform runner to cancel (returning True) or not (returning False)
    :param finished_callback: An optional callback that will be invoked at shutdown after process cleanup.
    :param status_handler: An optional callback that will be invoked any time the status changes (e.g...started, running, failed, successful, timeout)
    :param artifacts_handler: An optional callback that will be invoked at the end of the run to deal with the artifacts from the run.
    :param check_job_event_data: Check if job events data is completely generated. If event data is not completely generated and if
                                 value is set to 'True' it will raise 'AnsibleRunnerException' exception,
                                 if set to 'False' it log a debug message and continue execution. Default value is 'False'
    :type action: str
    :type config_file: str
    :type only_changed: bool
    :type runner_mode: str
    :type host_cwd: str
    :type envvars: dict
    :type passwords: dict
    :type settings: dict
    :type private_data_dir: str
    :type project_dir: str
    :type artifact_dir: str
    :type fact_cache_type: str
    :type fact_cache: str
    :type process_isolation: bool
    :type process_isolation_executable: str
    :type container_image: str
    :type container_volume_mounts: list
    :type container_options: list
    :type container_workdir: str
    :type ident: str
    :type rotate_artifacts: int
    :type timeout: int
    :type ssh_key: str
    :type quiet: bool
    :type json_mode: bool
    :type event_handler: Callable
    :type cancel_callback: Callable
    :type finished_callback: Callable
    :type status_handler: Callable
    :type artifacts_handler: Callable
    :type check_job_event_data: bool

    :returns: Returns a tuple of response and error string. In case if ``runner_mode`` is set to ``pexpect`` the error value is
              empty as ``pexpect`` uses same output descriptor for stdout and stderr.
    '''
    event_callback_handler = kwargs.pop('event_handler', None)
    status_callback_handler = kwargs.pop('status_handler', None)
    artifacts_handler = kwargs.pop('artifacts_handler', None)
    cancel_callback = kwargs.pop('cancel_callback', None)
    finished_callback = kwargs.pop('finished_callback', None)

    rd = AnsibleCfgConfig(**kwargs)
    rd.prepare_ansible_config_command(action=action, config_file=config_file, only_changed=only_changed)
    r = Runner(rd,
               event_handler=event_callback_handler,
               status_handler=status_callback_handler,
               artifacts_handler=artifacts_handler,
               cancel_callback=cancel_callback,
               finished_callback=finished_callback)
    r.run()
    with r.stdout as stdout, r.stderr as stderr:
        response = stdout.read()
        error = stderr.read()
    return response, error


def get_role_list(collection=None, playbook_dir=None, **kwargs):
    '''
    Run an ``ansible-doc`` command to get list of installed collection roles.

    Only roles that have an argument specification defined are returned.

    .. note:: Version added: 2.2

    :param str collection: A fully qualified collection name used to filter the results.
    :param str playbook_dir: This parameter is used to set the relative path to handle playbook adjacent installed roles.

    :param str runner_mode: The applicable values are ``pexpect`` and ``subprocess``. Default is set to ``subprocess``.
    :param str host_cwd: The host current working directory to be mounted within the container (if enabled) and will be
                     the work directory within container.
    :param dict envvars: Environment variables to be used when running Ansible. Environment variables will also be
                    read from ``env/envvars`` in ``private_data_dir``
    :param dict passwords: A dictionary containing password prompt patterns and response values used when processing output from
                      Ansible. Passwords will also be read from ``env/passwords`` in ``private_data_dir``.
    :param dict settings: A dictionary containing settings values for the ``ansible-runner`` runtime environment. These will also
                     be read from ``env/settings`` in ``private_data_dir``.
    :param str ssh_key: The ssh private key passed to ``ssh-agent`` as part of the ansible-playbook run.
    :param bool quiet: Disable all output
    :param bool json_mode: Store event data in place of stdout on the console and in the stdout file
    :param str artifact_dir: The path to the directory where artifacts should live, this defaults to 'artifacts' under the private data dir
    :param str project_dir: The path to the playbook content, this defaults to 'project' within the private data dir
    :param int rotate_artifacts: Keep at most n artifact directories, disable with a value of 0 which is the default
    :param int timeout: The timeout value in seconds that will be passed to either ``pexpect`` of ``subprocess`` invocation
        (based on ``runner_mode`` selected) while executing command. If the timeout is triggered, it will force cancel the execution.
    :param bool process_isolation: Enable process isolation using a container engine, such as podman.
    :param str process_isolation_executable: Process isolation executable or container engine used to isolate execution. (default: podman)
    :param str container_image: Container image to use when running an Ansible task
    :param list container_volume_mounts: List of bind mounts in the form ``host_dir:/container_dir:labels``. (default: None)
    :param list container_options: List of container options to pass to execution engine.
    :param str container_workdir: The working directory within the container.
    :param str fact_cache: A string that will be used as the name for the subdirectory of the fact cache in artifacts directory.
                       This is only used for 'jsonfile' type fact caches.
    :param str fact_cache_type: A string of the type of fact cache to use.  Defaults to 'jsonfile'.
    :param str private_data_dir: The directory containing all runner metadata needed to invoke the runner
        module. Output artifacts will also be stored here for later consumption.
    :param str ident: The run identifier for this invocation of Runner. Will be used to create and name
        the artifact directory holding the results of the invocation.
    :param Callable event_handler: An optional callback that will be invoked any time an event is received by Runner itself, return True to keep the event
    :param Callable cancel_callback: An optional callback that can inform runner to cancel (returning True) or not (returning False)
    :param Callable finished_callback: An optional callback that will be invoked at shutdown after process cleanup.
    :param Callable status_handler: An optional callback that will be invoked any time the status changes
        (for example: started, running, failed, successful, timeout)
    :param Callable artifacts_handler: An optional callback that will be invoked at the end of the run to deal with the artifacts from the run.
    :param bool check_job_event_data: Check if job events data is completely generated. If event data is not completely generated and if
        value is set to 'True' it will raise 'AnsibleRunnerException' exception. If set to 'False', log a debug message and continue execution.
        Default value is 'False'

    :returns: A tuple of response and error string. The response is a dictionary object
        (as returned by ansible-doc JSON output) containing each role found, or an empty dict
        if none are found.
    '''
    event_callback_handler = kwargs.pop('event_handler', None)
    status_callback_handler = kwargs.pop('status_handler', None)
    artifacts_handler = kwargs.pop('artifacts_handler', None)
    cancel_callback = kwargs.pop('cancel_callback', None)
    finished_callback = kwargs.pop('finished_callback', None)

    rd = DocConfig(**kwargs)
    rd.prepare_role_list_command(collection, playbook_dir)
    r = Runner(rd,
               event_handler=event_callback_handler,
               status_handler=status_callback_handler,
               artifacts_handler=artifacts_handler,
               cancel_callback=cancel_callback,
               finished_callback=finished_callback)
    r.run()
    with r.stdout as stdout, r.stderr as stderr:
        response = stdout.read()
        error = stderr.read()
    if response:
        response = json.loads(sanitize_json_response(response))
    return response, error


def get_role_argspec(role, collection=None, playbook_dir=None, **kwargs):
    '''
    Run an ``ansible-doc`` command to get a role argument specification.

    .. note:: Version added: 2.2

    :param str role: Simple role name, or fully qualified collection role name, to query.
    :param str collection: If specified, will be combined with the role name to form a fully qualified collection role name.
        If this is supplied, the ``role`` param should not be fully qualified.
    :param str playbook_dir: This parameter is used to set the relative path to handle playbook adjacent installed roles.

    :param str runner_mode: The applicable values are ``pexpect`` and ``subprocess``. Default is set to ``subprocess``.
    :param str host_cwd: The host current working directory to be mounted within the container (if enabled) and will be
                     the work directory within container.
    :param dict envvars: Environment variables to be used when running Ansible. Environment variables will also be
                    read from ``env/envvars`` in ``private_data_dir``
    :param dict passwords: A dictionary containing password prompt patterns and response values used when processing output from
                      Ansible. Passwords will also be read from ``env/passwords`` in ``private_data_dir``.
    :param dict settings: A dictionary containing settings values for the ``ansible-runner`` runtime environment. These will also
                     be read from ``env/settings`` in ``private_data_dir``.
    :param str ssh_key: The ssh private key passed to ``ssh-agent`` as part of the ansible-playbook run.
    :param bool quiet: Disable all output
    :param bool json_mode: Store event data in place of stdout on the console and in the stdout file
    :param str artifact_dir: The path to the directory where artifacts should live, this defaults to 'artifacts' under the private data dir
    :param str project_dir: The path to the playbook content, this defaults to 'project' within the private data dir
    :param int rotate_artifacts: Keep at most n artifact directories, disable with a value of 0 which is the default
    :param int timeout: The timeout value in seconds that will be passed to either ``pexpect`` of ``subprocess`` invocation
        (based on ``runner_mode`` selected) while executing command. If the timeout is triggered, it will force cancel the execution.
    :param bool process_isolation: Enable process isolation using a container engine, such as podman.
    :param str process_isolation_executable: Process isolation executable or container engine used to isolate execution. (default: podman)
    :param str container_image: Container image to use when running an Ansible task
    :param list container_volume_mounts: List of bind mounts in the form ``host_dir:/container_dir:labels``. (default: None)
    :param list container_options: List of container options to pass to execution engine.
    :param str container_workdir: The working directory within the container.
    :param str fact_cache: A string that will be used as the name for the subdirectory of the fact cache in artifacts directory.
                       This is only used for 'jsonfile' type fact caches.
    :param str fact_cache_type: A string of the type of fact cache to use.  Defaults to 'jsonfile'.
    :param str private_data_dir: The directory containing all runner metadata needed to invoke the runner
        module. Output artifacts will also be stored here for later consumption.
    :param str ident: The run identifier for this invocation of Runner. Will be used to create and name
        the artifact directory holding the results of the invocation.
    :param Callable event_handler: An optional callback that will be invoked any time an event is received by Runner itself, return True to keep the event
    :param Callable cancel_callback: An optional callback that can inform runner to cancel (returning True) or not (returning False)
    :param Callable finished_callback: An optional callback that will be invoked at shutdown after process cleanup.
    :param Callable status_handler: An optional callback that will be invoked any time the status changes
        (for example: started, running, failed, successful, timeout)
    :param Callable artifacts_handler: An optional callback that will be invoked at the end of the run to deal with the artifacts from the run.
    :param bool check_job_event_data: Check if job events data is completely generated. If event data is not completely generated and if
        value is set to 'True' it will raise 'AnsibleRunnerException' exception. If set to 'False', log a debug message and continue execution.
        Default value is 'False'

    :returns: A tuple of response and error string. The response is a dictionary object
        (as returned by ansible-doc JSON output) containing each role found, or an empty dict
        if none are found.
    '''
    event_callback_handler = kwargs.pop('event_handler', None)
    status_callback_handler = kwargs.pop('status_handler', None)
    artifacts_handler = kwargs.pop('artifacts_handler', None)
    cancel_callback = kwargs.pop('cancel_callback', None)
    finished_callback = kwargs.pop('finished_callback', None)

    rd = DocConfig(**kwargs)
    rd.prepare_role_argspec_command(role, collection, playbook_dir)
    r = Runner(rd,
               event_handler=event_callback_handler,
               status_handler=status_callback_handler,
               artifacts_handler=artifacts_handler,
               cancel_callback=cancel_callback,
               finished_callback=finished_callback)
    r.run()
    with r.stdout as stdout, r.stderr as stderr:
        response = stdout.read()
        error = stderr.read()
    if response:
        response = json.loads(sanitize_json_response(response))
    return response, error
