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

    See parameters given to :py:func:`ansible_runner.interface.run`
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

    :param private_data_dir: The directory containing all runner metadata needed to invoke the runner
                             module. Output artifacts will also be stored here for later consumption.
    :param ident: The run identifier for this invocation of Runner. Will be used to create and name
                  the artifact directory holding the results of the invocation.
    :param playbook: The playbook (either supplied here as a list or string... or as a path relative to
                     ``private_data_dir/project``) that will be invoked by runner when executing Ansible.
    :param inventory: Overridees the inventory directory/file (supplied at ``private_data_dir/inventory``) with
                      a specific host or list of hosts. This can take the form of
      - Path to the inventory file in the ``private_data_dir``
      - Native python dict supporting the YAML/json inventory structure
      - A text INI formatted string
    :param envvars: Environment variables to be used when running Ansible. Environment variables will also be
                    read from ``env/envvars`` in ``private_data_dir``
    :param extravars: Extra variables to be passed to Ansible at runtime using ``-e``. Extra vars will also be
                      read from ``env/extravars`` in ``private_data_dir``.
    :param passwords: A dictionary containing password prompt patterns and response values used when processing output from
                      Ansible. Passwords will also be read from ``env/passwords`` in ``private_data_dir``.
    :param settings: A dictionary containing settings values for the ``ansible-runner`` runtime environment. These will also
                     be read from ``env/settings`` in ``private_data_dir``.
    :param ssh_key: The ssh private key passed to ``ssh-agent`` as part of the ansible-playbook run.
    :param limit: Matches ansible's ``--limit`` parameter to further constrain the inventory to be used
    :param verbosity: Control how verbose the output of ansible-playbook is
    :type private_data_dir: str
    :type ident: str
    :type playbook: str or filename or list
    :type inventory: str or dict or list
    :type envvars: dict
    :type extravars: dict
    :type passwords: dict
    :type settings: dict
    :type ssh_key: str
    :type verbosity: int

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
