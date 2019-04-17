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
import atexit
import os
import re
import pexpect
import stat
import shlex
import shutil
import tempfile
import logging

import six
from uuid import uuid4
try:
    from collections.abc import Mapping
except ImportError:
    from collections import Mapping

from distutils.dir_util import copy_tree

from six import iteritems, string_types

from ansible_runner import output
from ansible_runner.exceptions import ConfigurationError
from ansible_runner.loader import ArtifactLoader
from ansible_runner.utils import (
    open_fifo_write,
    args2cmdline,
)

logger = logging.getLogger('ansible-runner')


class ExecutionMode():
    NONE = 0
    ANSIBLE = 1
    ANSIBLE_PLAYBOOK = 2
    RAW = 3


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
                 inventory=None, roles_path=None, limit=None, module=None, module_args=None,
                 verbosity=None, quiet=False, json_mode=False, artifact_dir=None,
                 rotate_artifacts=0, host_pattern=None, binary=None, extravars=None, suppress_ansible_output=False,
                 process_isolation=False, process_isolation_executable=None, process_isolation_path=None,
                 process_isolation_hide_paths=None, process_isolation_show_paths=None, process_isolation_ro_paths=None,
                 tags=None, skip_tags=None, fact_cache_type='jsonfile', fact_cache=None, project_dir=None,
                 directory_isolation_base_path=None, envvars=None, forks=None):
        self.private_data_dir = os.path.abspath(private_data_dir)
        self.ident = ident
        self.json_mode = json_mode
        self.playbook = playbook
        self.inventory = inventory
        self.roles_path = roles_path
        self.limit = limit
        self.module = module
        self.module_args = module_args
        self.host_pattern = host_pattern
        self.binary = binary
        self.rotate_artifacts = rotate_artifacts
        self.artifact_dir = os.path.abspath(artifact_dir or self.private_data_dir)
        if self.ident is None:
            self.artifact_dir = os.path.join(self.artifact_dir, "artifacts")
        else:
            self.artifact_dir = os.path.join(self.artifact_dir, "artifacts", "{}".format(self.ident))

        self.extra_vars = extravars
        self.process_isolation = process_isolation
        self.process_isolation_executable = process_isolation_executable
        self.process_isolation_path = process_isolation_path
        self.process_isolation_hide_paths = process_isolation_hide_paths
        self.process_isolation_show_paths = process_isolation_show_paths
        self.process_isolation_ro_paths = process_isolation_ro_paths
        self.directory_isolation_path = directory_isolation_base_path
        if not project_dir:
            self.project_dir = os.path.join(self.private_data_dir, 'project')
        else:
            self.project_dir = project_dir
        self.verbosity = verbosity
        self.quiet = quiet
        self.suppress_ansible_output = suppress_ansible_output
        self.loader = ArtifactLoader(self.private_data_dir)
        self.tags = tags
        self.skip_tags = skip_tags
        self.fact_cache_type = fact_cache_type
        self.fact_cache = os.path.join(self.artifact_dir, fact_cache or 'fact_cache') if self.fact_cache_type == 'jsonfile' else None
        self.execution_mode = ExecutionMode.NONE
        self.envvars = envvars
        self.forks = forks

    def prepare(self):
        """
        Performs basic checks and then properly invokes

        - prepare_inventory
        - prepare_env
        - prepare_command

        It's also responsible for wrapping the command with the proper ssh agent invocation
        and setting early ANSIBLE_ environment variables.
        """
        # ansible_path = find_executable('ansible')
        # if ansible_path is None or not os.access(ansible_path, os.X_OK):
        #     raise ConfigurationError("Ansible not found. Make sure that it is installed.")
        if self.private_data_dir is None:
            raise ConfigurationError("Runner Base Directory is not defined")
        if self.module and self.playbook:
            raise ConfigurationError("Only one of playbook and module options are allowed")
        if not os.path.exists(self.artifact_dir):
            os.makedirs(self.artifact_dir, mode=0o700)
        if self.directory_isolation_path is not None:
            self.directory_isolation_path = tempfile.mkdtemp(prefix='runner_di_', dir=self.directory_isolation_path)
            if os.path.exists(self.project_dir):
                output.debug("Copying directory tree from {} to {} for working directory isolation".format(self.project_dir,
                                                                                                           self.directory_isolation_path))
                copy_tree(self.project_dir, self.directory_isolation_path, preserve_symlinks=True)

        self.prepare_inventory()
        self.prepare_env()
        self.prepare_command()

        if self.execution_mode == ExecutionMode.ANSIBLE_PLAYBOOK and self.playbook is None:
            raise ConfigurationError("Runner playbook required when running ansible-playbook")
        elif self.execution_mode == ExecutionMode.ANSIBLE and self.module is None:
            raise ConfigurationError("Runner module required when running ansible")
        elif self.execution_mode == ExecutionMode.NONE:
            raise ConfigurationError("No executable for runner to run")

        # write the SSH key data into a fifo read by ssh-agent
        if self.ssh_key_data:
            self.ssh_key_path = os.path.join(self.artifact_dir, 'ssh_key_data')
            open_fifo_write(self.ssh_key_path, self.ssh_key_data)
            self.command = self.wrap_args_with_ssh_agent(self.command, self.ssh_key_path)

        # Use local callback directory
        callback_dir = self.env.get('AWX_LIB_DIRECTORY', os.getenv('AWX_LIB_DIRECTORY'))
        if callback_dir is None:
            callback_dir = os.path.join(os.path.split(os.path.abspath(__file__))[0],
                                        "callbacks")
        python_path = self.env.get('PYTHONPATH', os.getenv('PYTHONPATH', ''))
        if python_path and not python_path.endswith(':'):
            python_path += ':'
        self.env['ANSIBLE_CALLBACK_PLUGINS'] = callback_dir
        if 'AD_HOC_COMMAND_ID' in self.env:
            self.env['ANSIBLE_STDOUT_CALLBACK'] = 'minimal'
        else:
            self.env['ANSIBLE_STDOUT_CALLBACK'] = 'awx_display'
        self.env['ANSIBLE_RETRY_FILES_ENABLED'] = 'False'
        self.env['ANSIBLE_HOST_KEY_CHECKING'] = 'False'
        self.env['AWX_ISOLATED_DATA_DIR'] = self.artifact_dir

        self.env['PYTHONPATH'] = python_path + callback_dir
        if self.roles_path:
            self.env['ANSIBLE_ROLES_PATH'] = ':'.join(self.roles_path)

        if self.process_isolation:
            self.command = self.wrap_args_with_process_isolation(self.command)

        if self.fact_cache_type == 'jsonfile':
            self.env['ANSIBLE_CACHE_PLUGIN'] = 'jsonfile'
            self.env['ANSIBLE_CACHE_PLUGIN_CONNECTION'] = self.fact_cache

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
        except ConfigurationError:
            output.debug('Not loading passwords')
            self.expect_passwords = dict()
        self.expect_passwords[pexpect.TIMEOUT] = None
        self.expect_passwords[pexpect.EOF] = None

        try:
            # seed env with existing shell env
            self.env = os.environ.copy()
            envvars = self.loader.load_file('env/envvars', Mapping)
            if envvars:
                self.env.update({k:six.text_type(v) for k, v in envvars.items()})
            if self.envvars and isinstance(self.envvars, dict):
                self.env.update({k:six.text_type(v) for k, v in self.envvars.items()})
        except ConfigurationError:
            output.debug("Not loading environment vars")
            # Still need to pass default environment to pexpect
            self.env = os.environ.copy()

        try:
            self.settings = self.loader.load_file('env/settings', Mapping)
        except ConfigurationError:
            output.debug("Not loading settings")
            self.settings = dict()

        try:
            self.ssh_key_data = self.loader.load_file('env/ssh_key', string_types)
        except ConfigurationError:
            output.debug("Not loading ssh key")
            self.ssh_key_data = None

        self.idle_timeout = self.settings.get('idle_timeout', None)
        self.job_timeout = self.settings.get('job_timeout', None)
        self.pexpect_timeout = self.settings.get('pexpect_timeout', 5)

        self.process_isolation = self.settings.get('process_isolation', self.process_isolation)
        self.process_isolation_executable = self.settings.get('process_isolation_executable', self.process_isolation_executable)
        self.process_isolation_path = self.settings.get('process_isolation_path', self.process_isolation_path)
        self.process_isolation_hide_paths = self.settings.get('process_isolation_hide_paths', self.process_isolation_hide_paths)
        self.process_isolation_show_paths = self.settings.get('process_isolation_show_paths', self.process_isolation_show_paths)
        self.process_isolation_ro_paths = self.settings.get('process_isolation_ro_paths', self.process_isolation_ro_paths)

        self.pexpect_use_poll = self.settings.get('pexpect_use_poll', True)
        self.suppress_ansible_output = self.settings.get('suppress_ansible_output', self.quiet)
        self.directory_isolation_cleanup = bool(self.settings.get('directory_isolation_cleanup', True))

        if 'AD_HOC_COMMAND_ID' in self.env or not os.path.exists(self.project_dir):
            self.cwd = self.private_data_dir
        else:
            if self.directory_isolation_path is not None:
                self.cwd = self.directory_isolation_path
            else:
                self.cwd = self.project_dir

        if 'fact_cache' in self.settings:
            if 'fact_cache_type' in self.settings:
                if self.settings['fact_cache_type'] == 'jsonfile':
                    self.fact_cache = os.path.join(self.artifact_dir, self.settings['fact_cache'])
            else:
                self.fact_cache = os.path.join(self.artifact_dir, self.settings['fact_cache'])

    def prepare_command(self):
        """
        Determines if the literal ``ansible`` or ``ansible-playbook`` commands are given
        and if not calls :py:meth:`ansible_runner.runner_config.RunnerConfig.generate_ansible_command`
        """
        try:
            cmdline_args = self.loader.load_file('args', string_types)
            self.command = shlex.split(cmdline_args.decode('utf-8'))
            self.execution_mode = ExecutionMode.RAW
        except ConfigurationError:
            self.command = self.generate_ansible_command()

    def generate_ansible_command(self):
        """
        Given that the ``RunnerConfig`` preparation methods have been run to gather the inputs this method
        will generate the ``ansible`` or ``ansible-playbook`` command that will be used by the
        :py:class:`ansible_runner.runner.Runner` object to start the process
        """
        if self.binary is not None:
            base_command = self.binary
            self.execution_mode = ExecutionMode.RAW
        elif self.module is not None:
            base_command = 'ansible'
            self.execution_mode = ExecutionMode.ANSIBLE
        else:
            base_command = 'ansible-playbook'
            self.execution_mode = ExecutionMode.ANSIBLE_PLAYBOOK

        exec_list = [base_command]

        try:
            cmdline_args = self.loader.load_file('env/cmdline', string_types, encoding=None)
            args = shlex.split(cmdline_args)
            exec_list.extend(args)
        except ConfigurationError:
            pass

        if isinstance(self.inventory, list):
            for i in self.inventory:
                exec_list.append("-i")
                exec_list.append(i)
        else:
            exec_list.append("-i")
            exec_list.append(self.inventory)

        if self.limit is not None:
            exec_list.append("--limit")
            exec_list.append(self.limit)

        if self.loader.isfile('env/extravars'):
            exec_list.extend(['-e', '@{}'.format(self.loader.abspath('env/extravars'))])
        if isinstance(self.extra_vars, dict) and self.extra_vars:
            exec_list.extend(
                [
                    '-e',
                    '%s' % ' '.join(
                        ["{}=\"{}\"".format(k, self.extra_vars[k]) for k in self.extra_vars]
                    )
                ]
            )
        if self.verbosity:
            v = 'v' * self.verbosity
            exec_list.append('-{}'.format(v))

        if self.tags:
            exec_list.extend(['--tags', '{}'.format(self.tags)])

        if self.skip_tags:
            exec_list.extend(['--skip-tags', '{}'.format(self.skip_tags)])

        if self.forks:
            exec_list.extend(['--forks', '{}'.format(self.forks)])

        # Other parameters
        if self.execution_mode == ExecutionMode.ANSIBLE_PLAYBOOK:
            exec_list.append(self.playbook)
        elif self.execution_mode == ExecutionMode.ANSIBLE:
            exec_list.append("-m")
            exec_list.append(self.module)

            if self.module_args is not None:
                exec_list.append("-a")
                exec_list.append(self.module_args)

            if self.host_pattern is not None:
                exec_list.append(self.host_pattern)

        return exec_list

    def build_process_isolation_temp_dir(self):
        '''
        Create a temporary directory for process isolation to use.
        '''
        path = tempfile.mkdtemp(prefix='ansible_runner_pi_', dir=self.process_isolation_path)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        atexit.register(shutil.rmtree, path)
        return path

    def wrap_args_with_process_isolation(self, args):
        '''
        Wrap existing command line with bwrap to restrict access to:
         - self.process_isolation_path (generally, /tmp) (except for own /tmp files)
        '''
        cwd = os.path.realpath(self.cwd)
        pi_temp_dir = self.build_process_isolation_temp_dir()
        new_args = [self.process_isolation_executable or 'bwrap', '--unshare-pid', '--dev-bind', '/', '/', '--proc', '/proc']

        for path in sorted(set(self.process_isolation_hide_paths or [])):
            if not os.path.exists(path):
                logger.debug('hide path not found: {0}'.format(path))
                continue
            path = os.path.realpath(path)
            if os.path.isdir(path):
                new_path = tempfile.mkdtemp(dir=pi_temp_dir)
                os.chmod(new_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            else:
                handle, new_path = tempfile.mkstemp(dir=pi_temp_dir)
                os.close(handle)
                os.chmod(new_path, stat.S_IRUSR | stat.S_IWUSR)
            new_args.extend(['--bind', '{0}'.format(new_path), '{0}'.format(path)])

        if self.private_data_dir:
            show_paths = [self.private_data_dir]
        else:
            show_paths = [cwd]

        for path in sorted(set(self.process_isolation_ro_paths or [])):
            if not os.path.exists(path):
                logger.debug('read-only path not found: {0}'.format(path))
                continue
            path = os.path.realpath(path)
            new_args.extend(['--ro-bind', '{0}'.format(path),  '{0}'.format(path)])

        show_paths.extend(self.process_isolation_show_paths or [])
        for path in sorted(set(show_paths)):
            if not os.path.exists(path):
                logger.debug('show path not found: {0}'.format(path))
                continue
            path = os.path.realpath(path)
            new_args.extend(['--bind', '{0}'.format(path), '{0}'.format(path)])

        if self.execution_mode == ExecutionMode.ANSIBLE_PLAYBOOK:
            # playbook runs should cwd to the SCM checkout dir
            if self.directory_isolation_path is not None:
                new_args.extend(['--chdir', os.path.realpath(self.directory_isolation_path)])
            else:
                new_args.extend(['--chdir', self.project_dir])
        elif self.execution_mode == ExecutionMode.ANSIBLE:
            # ad-hoc runs should cwd to the root of the private data dir
            new_args.extend(['--chdir', os.path.realpath(self.private_data_dir)])

        new_args.extend(args)
        return new_args

    def wrap_args_with_ssh_agent(self, args, ssh_key_path, ssh_auth_sock=None, silence_ssh_add=False):
        """
        Given an existing command line and parameterization this will return the same command line wrapped with the
        necessary calls to ``ssh-agent``
        """
        if ssh_key_path:
            ssh_add_command = args2cmdline('ssh-add', ssh_key_path)
            if silence_ssh_add:
                ssh_add_command = ' '.join([ssh_add_command, '2>/dev/null'])
            cmd = ' && '.join([ssh_add_command,
                               args2cmdline('rm', '-f', ssh_key_path),
                               args2cmdline(*args)])
            args = ['ssh-agent']
            if ssh_auth_sock:
                args.extend(['-a', ssh_auth_sock])
            args.extend(['sh', '-c', cmd])
        return args

