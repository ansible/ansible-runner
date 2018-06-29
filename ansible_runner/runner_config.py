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
import re
import pipes
import threading
import pexpect
import stat
import shlex

from uuid import uuid4
from collections import Mapping

from six import iteritems, string_types

from ansible_runner import output
from ansible_runner.exceptions import ConfigurationError
from ansible_runner.loader import ArtifactLoader


class RunnerConfig(object):
    """
    A ``Runner`` configuration object that's meant to encapsulate the configuration used by the
    :py:mod:`ansible_runner.runner.Runner` object to launch and manage the invocation of ``ansible``
    and ``ansible-playbook``

    Typically this object is initialized for you when using the standard ``run`` interfaces in :py:mod:`ansible_runner.interface`
    but can be used to construct the ``Runner`` configuration to be invoked elsewhere. It can also be overridden to provide different
    functionality to the Runner object.

    :Example:

    >>> rc = RunnerConfig(...)
    >>> r = Runner(config=rc)
    >>> r.run()

    """

    def __init__(self,
                 private_data_dir=None, playbook=None, ident=uuid4(),
                 inventory=None, limit=None, module=None, module_args=None,
                 verbosity=None, quiet=False, json_mode=False, artifact_dir=None):
        self.private_data_dir = os.path.abspath(private_data_dir)
        self.ident = ident
        self.json_mode = json_mode
        self.playbook = playbook
        self.inventory = inventory
        self.limit = limit
        self.module = module
        self.module_args = module_args
        self.artifact_dir = artifact_dir or self.private_data_dir
        if self.ident is None:
            self.artifact_dir = os.path.join(self.artifact_dir, "artifacts")
        else:
            self.artifact_dir = os.path.join(self.artifact_dir, "artifacts", "{}".format(self.ident))

        self.extra_vars = None
        self.verbosity = verbosity
        self.quiet = quiet
        self.loader = ArtifactLoader(self.private_data_dir)

    def prepare(self):
        """
        Performs basic checks and then properly invokes

        - prepare_inventory
        - prepare_env
        - prepare_command

        It's also responsible for wrapping the command with the proper ssh agent invocation
        and setting early ANSIBLE_ environment variables.
        """
        if self.private_data_dir is None:
            raise ConfigurationError("Runner Base Directory is not defined")
        if self.playbook is None: # TODO: ad-hoc mode, module and args
            raise ConfigurationError("Runner playbook is not defined")
        if not os.path.exists(self.artifact_dir):
            os.makedirs(self.artifact_dir)

        self.prepare_inventory()
        self.prepare_env()
        self.prepare_command()

        # write the SSH key data into a fifo read by ssh-agent
        if self.ssh_key_data:
            self.ssh_key_path = os.path.join(self.artifact_dir, 'ssh_key_data')
            self.ssh_auth_sock = os.path.join(self.artifact_dir, 'ssh_auth.sock')
            self.open_fifo_write(self.ssh_key_path, self.ssh_key_data)
            self.command = self.wrap_args_with_ssh_agent(self.command, self.ssh_key_path, self.ssh_auth_sock)

        # Use local callback directory
        callback_dir = os.getenv('AWX_LIB_DIRECTORY')
        if callback_dir is None:
            callback_dir = os.path.join(os.path.split(os.path.abspath(__file__))[0],
                                        "callbacks")
        self.env['ANSIBLE_CALLBACK_PLUGINS'] = callback_dir
        if 'AD_HOC_COMMAND_ID' in self.env:
            self.env['ANSIBLE_STDOUT_CALLBACK'] = 'minimal'
        else:
            self.env['ANSIBLE_STDOUT_CALLBACK'] = 'awx_display'
        self.env['ANSIBLE_RETRY_FILES_ENABLED'] = 'False'
        self.env['ANSIBLE_HOST_KEY_CHECKING'] = 'False'
        self.env['AWX_ISOLATED_DATA_DIR'] = self.artifact_dir
        self.env['PYTHONPATH'] = self.env.get('PYTHONPATH', '') + callback_dir + ':'

    def prepare_inventory(self):
        """
        Prepares the inventory default under ``private_data_dir`` if it's not overridden by the constructor.
        """
        if self.inventory is None:
            self.inventory  = os.path.join(self.private_data_dir, "inventory")

    def prepare_env(self):
        """
        Manages reading environment metadata files under ``private_data_dir`` and merging/updating
        with existing values so the :py:class:`ansible_runner.runner.Runner` object can read and use them easily
        """
        try:
            passwords = self.loader.load_file('env/passwords', Mapping)
            self.expect_passwords = {
                re.compile(pattern, re.M): password
                for pattern, password in iteritems(passwords)
            }
        except ConfigurationError as exc:
            output.display('Not loading passwords')
            self.expect_passwords = dict()
        self.expect_passwords[pexpect.TIMEOUT] = None
        self.expect_passwords[pexpect.EOF] = None

        try:
            # seed env with existing shell env
            self.env = os.environ.copy()
            envvars = self.loader.load_file('env/envvars', Mapping)
            if envvars:
                self.env.update({k:str(v) for k, v in envvars.items()})
        except ConfigurationError as exc:
            output.display("Not loading environment vars")
            # Still need to pass default environment to pexpect
            self.env = os.environ.copy()

        if self.loader.isfile('env/extravars'):
            self.extra_vars = self.loader.abspath('env/extravars')

        try:
            self.settings = self.loader.load_file('env/settings', Mapping)
        except ConfigurationError as exc:
            output.display("Not loading settings")
            self.settings = dict()

        try:
            self.ssh_key_data = self.loader.load_file('env/ssh_key', string_types)
        except ConfigurationError as exc:
            output.display("Not loading ssh key")
            self.ssh_key_data = None

        self.idle_timeout = self.settings.get('idle_timeout', 120)
        self.job_timeout = self.settings.get('job_timeout', 120)
        self.pexpect_timeout = self.settings.get('pexpect_timeout', 5)
        self.suppress_ansible_output = self.settings.get('suppress_ansible_output', self.quiet)

        if 'AD_HOC_COMMAND_ID' in self.env:
            self.cwd = self.private_data_dir
        else:
            self.cwd = os.path.join(self.private_data_dir, 'project')

    def prepare_command(self):
        """
        Determines if the literal ``ansible`` or ``ansible-playbook`` commands are given
        and if not calls :py:meth:`ansible_runner.runner_config.RunnerConfig.generate_ansible_command`
        """
        try:
            self.command = self.loader.load_file('args', string_types)
        except ConfigurationError:
            self.command = self.generate_ansible_command()


    def generate_ansible_command(self):
        """
        Given that the ``RunnerConfig`` preparation methods have been run to gather the inputs this method
        will generate the ``ansible`` or ``ansible-playbook`` command that will be used by the
        :py:class:`ansible_runner.runner.Runner` object to start the process
        """
        if self.module is not None:
            base_command = 'ansible'
        else:
            base_command = 'ansible-playbook'

        exec_list = [base_command]

        try:
            cmdline_args = self.loader.load_file('env/cmdline', string_types)
            args = shlex.split(cmdline_args.decode('utf-8'))
            exec_list.extend(args)
        except ConfigurationError:
            pass

        exec_list.append("-i")
        exec_list.append(self.inventory)

        if self.limit is not None:
            exec_list.append("--limit")
            exec_list.append(self.limit)

        if self.extra_vars:
            exec_list.extend(['-e', '@%s' % self.extra_vars])
        if self.verbosity:
            v = 'v' * self.verbosity
            exec_list.append('-%s' % v)

        # Other parameters
        if base_command.endswith('ansible-playbook'):
            exec_list.append(self.playbook)

        elif base_command == 'ansible':
            exec_list.append("-m")
            exec_list.append(self.module)

            if self.module_args is not None:
                exec_list.append("-a")
                exec_list.append(self.module_args)

        return exec_list


    def wrap_args_with_ssh_agent(self, args, ssh_key_path, ssh_auth_sock=None, silence_ssh_add=False):
        """
        Given an existing command line and parameterization this will return the same command line wrapped with the
        necessary calls to ``ssh-agent``
        """
        if ssh_key_path:
            ssh_add_command = self.args2cmdline('ssh-add', ssh_key_path)
            if silence_ssh_add:
                ssh_add_command = ' '.join([ssh_add_command, '2>/dev/null'])
            cmd = ' && '.join([ssh_add_command,
                               self.args2cmdline('rm', '-f', ssh_key_path),
                               self.args2cmdline(*args)])
            args = ['ssh-agent']
            if ssh_auth_sock:
                args.extend(['-a', ssh_auth_sock])
            args.extend(['sh', '-c', cmd])
        return args


    def open_fifo_write(self, path, data):
        # TODO: Switch to utility function
        '''open_fifo_write opens the fifo named pipe in a new thread.
        This blocks the thread until an external process (such as ssh-agent)
        reads data from the pipe.
        '''
        os.mkfifo(path, stat.S_IRUSR | stat.S_IWUSR)
        threading.Thread(target=lambda p, d: open(p, 'wb').write(d),
                         args=(path, data)).start()

    def args2cmdline(self, *args):
        # TODO: switch to utility function
        return ' '.join([pipes.quote(a) for a in args])
