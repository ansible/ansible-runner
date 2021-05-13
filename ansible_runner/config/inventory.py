############################
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
import logging
from ansible_runner.config._base import BaseConfig, BaseExecutionMode
from ansible_runner.exceptions import ConfigurationError
from ansible_runner.utils import get_executable_path

logger = logging.getLogger('ansible-runner')


class InventoryConfig(BaseConfig):
    """
    A ``Runner`` configuration object that's meant to encapsulate the configuration used by the
    :py:mod:`ansible_runner.runner.InventoryConfig` object to launch and manage the invocation of
    command execution.

    Typically this object is initialized for you when using the standard ``get_inventory`` interfaces in :py:mod:`ansible_runner.interface`
    but can be used to construct the ``InventoryConfig`` configuration to be invoked elsewhere. It can also be overridden to provide different
    functionality to the InventoryConfig object.

    :Example:

    >>> ic = InventoryConfig(...)
    >>> r = Runner(config=ic)
    >>> r.run()

    """

    def __init__(self, runner_mode=None, **kwargs):
        # runner params
        self.runner_mode = runner_mode if runner_mode else 'subprocess'
        if self.runner_mode not in ['pexpect', 'subprocess']:
            raise ConfigurationError("Invalid runner mode {0}, valid value is either 'pexpect' or 'subprocess'".format(self.runner_mode))

        if kwargs.get("process_isolation"):
            self._ansible_inventory_exec_path = "ansible-inventory"
        else:
            self._ansible_inventory_exec_path = get_executable_path("ansible-inventory")

        self.execution_mode = BaseExecutionMode.ANSIBLE_COMMANDS
        super(InventoryConfig, self).__init__(**kwargs)

    _supported_response_formats = ('json', 'yaml', 'toml')
    _supported_actions = ('graph', 'host', 'list')

    def prepare_inventory_command(self, action, inventories, response_format=None, host=None,
                                  playbook_dir=None, vault_ids=None, vault_password_file=None,
                                  output_file=None, export=None):

        if action not in InventoryConfig._supported_actions:
            raise ConfigurationError("Invalid action {0}, valid value is one of either {1}".format(action, ", ".join(InventoryConfig._supported_actions)))

        if response_format and response_format not in InventoryConfig._supported_response_formats:
            raise ConfigurationError("Invalid response_format {0}, valid value is one of "
                                     "either {1}".format(response_format, ", ".join(InventoryConfig._supported_response_formats)))

        if not isinstance(inventories, list):
            raise ConfigurationError("inventories should be of type list, instead received {0} of type {1}".format(inventories, type(inventories)))

        if action == "host" and host is None:
            raise ConfigurationError("Value of host parameter is required when action in 'host'")

        if action == "graph" and response_format and response_format != 'json':
            raise ConfigurationError("'graph' action supports only 'json' response format")

        self._prepare_env(runner_mode=self.runner_mode)
        self.cmdline_args = []

        self.cmdline_args.append('--{0}'.format(action))
        if action == 'host':
            self.cmdline_args.append(host)

        for inv in inventories:
            self.cmdline_args.extend(['-i', inv])

        if response_format in ['yaml', 'toml']:
            self.cmdline_args.append('--{0}'.format(response_format))

        if playbook_dir:
            self.cmdline_args.extend(['--playbook-dir', playbook_dir])

        if vault_ids:
            self.cmdline_args.extend(['--vault-id', vault_ids])

        if vault_password_file:
            self.cmdline_args.extend(['--vault-password-file', vault_password_file])

        if output_file:
            self.cmdline_args.extend(['--output', output_file])

        if export:
            self.cmdline_args.append('--export')

        self.command = [self._ansible_inventory_exec_path] + self.cmdline_args
        self._handle_command_wrap(self.execution_mode, self.cmdline_args)
