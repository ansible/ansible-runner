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


class AnsibleCfgConfig(BaseConfig):
    """
    A ``Runner`` configuration object that's meant to encapsulate the configuration used by the
    :py:mod:`ansible_runner.runner.AnsibleCfgConfig` object to launch and manage the invocation of
    command execution.

    Typically this object is initialized for you when using the standard ``get_ansible_config`` interfaces in :py:mod:`ansible_runner.interface`
    but can be used to construct the ``AnsibleCfgConfig`` configuration to be invoked elsewhere. It can also be overridden to provide different
    functionality to the AnsibleCfgConfig object.

    :Example:

    >>> ac = AnsibleCfgConfig(...)
    >>> r = Runner(config=ac)
    >>> r.run()

    """

    def __init__(self, runner_mode=None, **kwargs):
        # runner params
        self.runner_mode = runner_mode if runner_mode else 'subprocess'
        if self.runner_mode not in ['pexpect', 'subprocess']:
            raise ConfigurationError("Invalid runner mode {0}, valid value is either 'pexpect' or 'subprocess'".format(self.runner_mode))

        if kwargs.get("process_isolation"):
            self._ansible_config_exec_path = "ansible-config"
        else:
            self._ansible_config_exec_path = get_executable_path("ansible-config")

        self.execution_mode = BaseExecutionMode.ANSIBLE_COMMANDS
        super(AnsibleCfgConfig, self).__init__(**kwargs)

    _supported_actions = ('list', 'dump', 'view')

    def prepare_ansible_config_command(self, action, config_file=None, only_changed=None):

        if action not in AnsibleCfgConfig._supported_actions:
            raise ConfigurationError("Invalid action {0}, valid value is one of either {1}".format(action, ", ".join(AnsibleCfgConfig._supported_actions)))

        if action != 'dump' and only_changed:
            raise ConfigurationError("only_changed is applicable for action 'dump'")
        self._prepare_env(runner_mode=self.runner_mode)
        self.cmdline_args = []

        self.cmdline_args.append(action)
        if config_file:
            self.cmdline_args.extend(['-c', config_file])

        if only_changed:
            self.cmdline_args.append('--only-changed')

        self.command = [self._ansible_config_exec_path] + self.cmdline_args
        self._handle_command_wrap(self.execution_mode, self.cmdline_args)
