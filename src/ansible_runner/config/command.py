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
import os

from ansible_runner.config._base import BaseConfig, BaseExecutionMode
from ansible_runner.exceptions import ConfigurationError

logger = logging.getLogger('ansible-runner')


class CommandConfig(BaseConfig):
    """
    A ``Runner`` configuration object that's meant to encapsulate the configuration used by the
    :py:mod:`ansible_runner.runner.CommandConfig` object to launch and manage the invocation of
    command execution.

    Typically this object is initialized for you when using the standard ``run`_command` interfaces in :py:mod:`ansible_runner.interface`
    but can be used to construct the ``CommandConfig`` configuration to be invoked elsewhere. It can also be overridden to provide different
    functionality to the CommandConfig object.
    :Example:

    >>> cc = CommandConfig(...)
    >>> r = Runner(config=cc)
    >>> r.run()
    """

    def __init__(self, input_fd=None, output_fd=None, error_fd=None, runner_mode=None, **kwargs):
        # subprocess runner mode params
        self.input_fd = input_fd
        self.output_fd = output_fd
        self.error_fd = error_fd

        if runner_mode == 'pexpect' and not self.input_fd:
            raise ConfigurationError("input_fd is applicable only with 'subprocess' runner mode")

        if runner_mode and runner_mode not in ['pexpect', 'subprocess']:
            raise ConfigurationError("Invalid runner mode {0}, valid value is either 'pexpect' or 'subprocess'".format(runner_mode))

        # runner params
        self.runner_mode = runner_mode

        self.execution_mode = BaseExecutionMode.NONE

        super(CommandConfig, self).__init__(**kwargs)

    _ANSIBLE_NON_INERACTIVE_CMDS = (
        'ansible-config',
        'ansible-doc',
        'ansible-galaxy',
    )

    def _set_runner_mode(self):
        if self.input_fd is not None or self.executable_cmd.split(os.pathsep)[-1] in CommandConfig._ANSIBLE_NON_INERACTIVE_CMDS:
            self.runner_mode = 'subprocess'
        else:
            self.runner_mode = 'pexpect'

    def prepare_run_command(self, executable_cmd, cmdline_args=None):
        self.executable_cmd = executable_cmd
        self.cmdline_args = cmdline_args

        if self.runner_mode is None:
            self._set_runner_mode()

        self._prepare_env(runner_mode=self.runner_mode)
        self._prepare_command()

        self._handle_command_wrap(self.execution_mode, self.cmdline_args)

    def _prepare_command(self):
        """
        Determines if it is ``ansible`` command or ``generic`` command and generate the command line
        """
        if not self.executable_cmd:
            raise ConfigurationError("For CommandRunner 'executable_cmd' value is required")

        if self.executable_cmd.split(os.pathsep)[-1].startswith('ansible'):
            self.execution_mode = BaseExecutionMode.ANSIBLE_COMMANDS
        else:
            self.execution_mode = BaseExecutionMode.GENERIC_COMMANDS

        if self.cmdline_args:
            self.command = [self.executable_cmd] + self.cmdline_args
        else:
            self.command = [self.executable_cmd]

        if self.execution_mode == BaseExecutionMode.GENERIC_COMMANDS \
           and 'python' in self.executable_cmd.split(os.pathsep)[-1] and self.cmdline_args is None:
            raise ConfigurationError("Runner requires python filename for execution")
        elif self.execution_mode == BaseExecutionMode.NONE:
            raise ConfigurationError("No executable for runner to run")
