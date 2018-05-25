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
import os
import logging

from ansible_runner.runner_config import RunnerConfig
from ansible_runner.runner import Runner
from ansible_runner.utils import dump_artifacts, configure_logging

logging.getLogger('ansible-runner').addHandler(logging.NullHandler())


def init_runner(**kwargs):
    '''
    Initialize the Runner() instance

    This function will properly initialize both run() and run_async()
    functions in the same way and return a value instance of Runner.
    '''
    dump_artifacts(kwargs)

    debug = kwargs.pop('debug', None)

    logfile = None
    if debug:
        logfile = os.path.join(kwargs['private_data_dir'], 'debug.log')

    configure_logging(filename=logfile, debug=debug)

    rc = RunnerConfig(**kwargs)
    rc.prepare()

    return Runner(rc)


def run(**kwargs):
    '''
    Run an Ansible Runner task in the foreground and return a Runner object when complete.

    Args:

        private_data_dir (string, path): The directory containing all runner metadata needed
            to invoke the runner module

        ident (string, optional): The run identifier for this invocation of Runner. Will be used
            to create and name the artifact directory holding the results of the invocation

        playbook (string, filename or list): The playbook relative path located in the private_data_dir/project
            directory that will be invoked by runner when executing Ansible.  If this value is provided as a
            Python list object, the playbook will be written to disk and then executed.

        inventory (string): Override the inventory directory/file supplied with runner metadata at
            private_data_dir/inventory with a specific list of hosts.  This kwarg accepts either a
            full path to the inventory file in the private_data_dir, a native Python dict supporting
            YAML inventory structure or a text INI formatted string.

        envvars (dict, optional): Any environment variables to be used when running Ansible.

        extravars (dict, optional): Any extra variables to be passed to Ansible at runtime using
            the -e option when calling ansible-playbook

        passwords (dict, optional): A dict object that contains password prompt patterns and response
            values used when processing output from ansible-playbook

        settings (dict, optional): A dict objec that contains values for ansible-runner runtime
            settings.

        ssh_key (string, optional): The ssh private key passed to ssh-agent as part of the
            ansible-playbook run

        limit (string, optional): Matches ansible's --limit parameter to further constrain the inventory to be used

    Returns:
        Runner: An object that holds details and results from the invocation of Ansible itself
    '''
    r = init_runner(**kwargs)
    r.run()
    return r


def run_async(**kwargs):
    '''
    Run an Ansible Runner task in the background and return a thread object and  Runner object when complete.

    Args:

        private_data_dir (string, path): The directory containing all runner metadata needed
            to invoke the runner module

        ident (string, optional): The run identifier for this invocation of Runner. Will be used
            to create and name the artifact directory holding the results of the invocation

        playbook (string, filename or list): The playbook relative path located in the private_data_dir/project
            directory that will be invoked by runner when executing Ansible.  If this value is provided as a
            Python list object, the playbook will be written to disk and then executed.

        inventory (string): Override the inventory directory/file supplied with runner metadata at
            private_data_dir/inventory with a specific list of hosts.  This kwarg accepts either a
            full path to the inventory file in the private_data_dir, a native Python dict supporting
            YAML inventory structure or a text INI formatted string.

        envvars (dict, optional): Any environment variables to be used when running Ansible.

        extravars (dict, optional): Any extra variables to be passed to Ansible at runtime using
            the -e option when calling ansible-playbook

        passwords (dict, optional): A dict object that contains password prompt patterns and response
            values used when processing output from ansible-playbook

        settings (dict, optional): A dict objec that contains values for ansible-runner runtime
            settings.

        ssh_key (string, optional): The ssh private key passed to ssh-agent as part of the
            ansible-playbook run

        limit (string, optional): Matches ansible's --limit parameter to further constrain the inventory to be used

    Returns:
        threadObj, Runner: An object representing the thread itself and a Runner instance that holds details
        and results from the invocation of Ansible itself
    '''
    r = init_runner(**kwargs)
    runner_thread = threading.Thread(target=r.run)
    runner_thread.start()
    return runner_thread, r
