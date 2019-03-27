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
import threading
import logging

from ansible_runner import output
from ansible_runner.runner_config import RunnerConfig
from ansible_runner.runner import Runner
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
    dump_artifacts(kwargs)

    debug = kwargs.pop('debug', None)
    logfile = kwargs.pop('logfile', None)

    if not kwargs.pop("ignore_logging", True):
        output.configure()
        if debug in (True, False):
            output.set_debug('enable' if debug is True else 'disable')

        if logfile:
            output.set_logfile(logfile)

    if kwargs.get("process_isolation", False):
        check_isolation_executable_installed(kwargs.get("process_isolation_executable", "bwrap"))

    event_callback_handler = kwargs.pop('event_handler', None)
    status_callback_handler = kwargs.pop('status_handler', None)
    cancel_callback = kwargs.pop('cancel_callback', None)
    finished_callback = kwargs.pop('finished_callback',  None)

    rc = RunnerConfig(**kwargs)
    rc.prepare()

    return Runner(rc,
                  event_handler=event_callback_handler,
                  status_handler=status_callback_handler,
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
    :param inventory: Overridees the inventory directory/file (supplied at ``private_data_dir/inventory``) with
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
    :param cmdline: Commnad line options passed to Ansible read from ``env/cmdline`` in ``private_data_dir``
    :param limit: Matches ansible's ``--limit`` parameter to further constrain the inventory to be used
    :param forks: Control Ansible parallel concurrency
    :param verbosity: Control how verbose the output of ansible-playbook is
    :param quiet: Disable all output
    :param artifact_dir: The path to the directory where artifacts should live, this defaults to 'artifacts' under the private data dir
    :param project_dir: The path to the playbook content, this defaults to 'project' within the private data dir
    :param rotate_artifacts: Keep at most n artifact directories, disable with a value of 0 which is the default
    :param event_handler: An optional callback that will be invoked any time an event is received by Runner itself
    :param cancel_callback: An optional callback that can inform runner to cancel (returning True) or not (returning False)
    :param finished_callback: An optional callback that will be invoked at shutdown after process cleanup.
    :param status_handler: An optional callback that will be invoked any time the status changes (e.g...started, running, failed, successful, timeout)
    :param process_isolation: Enable limiting what directories on the filesystem the playbook run has access to.
    :param process_isolation_executable: Path to the executable that will be used to provide filesystem isolation (default: bwrap)
    :param process_isolation_path: Path that an isolated playbook run will use for staging. (default: /tmp)
    :param process_isolation_hide_paths: A path or list of paths on the system that should be hidden from the playbook run.
    :param process_isolation_show_paths: A path or list of paths on the system that should be exposed to the playbook run.
    :param process_isolation_ro_paths: A path or list of paths on the system that should be exposed to the playbook run as read-only.
    :param directory_isolation_base_path: An optional path will be used as the base path to create a temp directory, the project contents will be
                                          copied to this location which will then be used as the working directory during playbook execution.
    :param fact_cache: A string that will be used as the name for the subdirectory of the fact cache in artifacts directory.
                       This is only used for 'jsonfile' type fact caches.
    :param fact_cache_type: A string of the type of fact cache to use.  Defaults to 'jsonfile'.
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
    :type event_handler: function
    :type cancel_callback: function
    :type finished_callback: function
    :type status_handler: function
    :type process_isolation: bool
    :type process_isolation_executable: str
    :type process_isolation_path: str
    :type process_isolation_hide_paths: str or list
    :type process_isolation_show_paths: str or list
    :type process_isolation_ro_paths: str or list
    :type directory_isolation_base_path: str
    :type fact_cache: str
    :type fact_cache_type: str

    :returns: A :py:class:`ansible_runner.runner.Runner` object
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
