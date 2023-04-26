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
import json
import logging
import os
import shlex
import stat
import tempfile
import six
import shutil

from six import string_types, text_type

from ansible_runner import output
from ansible_runner.config._base import BaseConfig, BaseExecutionMode
from ansible_runner.exceptions import ConfigurationError
from ansible_runner.output import debug
from ansible_runner.utils import register_for_cleanup


logger = logging.getLogger('ansible-runner')


class ExecutionMode():
    NONE = 0
    ANSIBLE = 1
    ANSIBLE_PLAYBOOK = 2
    RAW = 3


class RunnerConfig(BaseConfig):
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
                 private_data_dir, playbook=None, inventory=None, roles_path=None, limit=None,
                 module=None, module_args=None, verbosity=None, host_pattern=None, binary=None,
                 extravars=None, suppress_output_file=False, suppress_ansible_output=False, process_isolation_path=None,
                 process_isolation_hide_paths=None, process_isolation_show_paths=None,
                 process_isolation_ro_paths=None, tags=None, skip_tags=None,
                 directory_isolation_base_path=None, forks=None, cmdline=None, omit_event_data=False,
                 only_failed_event_data=False, **kwargs):

        self.runner_mode = "pexpect"

        super(RunnerConfig, self).__init__(private_data_dir, **kwargs)

        self.playbook = playbook
        self.inventory = inventory
        self.roles_path = roles_path
        self.limit = limit
        self.module = module
        self.module_args = module_args
        self.host_pattern = host_pattern
        self.binary = binary
        self.extra_vars = extravars
        self.process_isolation_path = process_isolation_path
        self.process_isolation_path_actual = None
        self.process_isolation_hide_paths = process_isolation_hide_paths
        self.process_isolation_show_paths = process_isolation_show_paths
        self.process_isolation_ro_paths = process_isolation_ro_paths
        self.directory_isolation_path = directory_isolation_base_path
        self.verbosity = verbosity
        self.suppress_output_file = suppress_output_file
        self.suppress_ansible_output = suppress_ansible_output
        self.tags = tags
        self.skip_tags = skip_tags
        self.execution_mode = ExecutionMode.NONE
        self.forks = forks
        self.cmdline_args = cmdline

        self.omit_event_data = omit_event_data
        self.only_failed_event_data = only_failed_event_data

    @property
    def sandboxed(self):
        return self.process_isolation and self.process_isolation_executable not in self._CONTAINER_ENGINES

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

        # Since the `sandboxed` property references attributes that may come from `env/settings`,
        # we must call prepare_env() before we can reference it.
        self.prepare_env()

        if self.sandboxed and self.directory_isolation_path is not None:
            self.directory_isolation_path = tempfile.mkdtemp(prefix='runner_di_', dir=self.directory_isolation_path)
            if os.path.exists(self.project_dir):
                output.debug("Copying directory tree from {} to {} for working directory isolation".format(self.project_dir,
                                                                                                           self.directory_isolation_path))
                shutil.copytree(self.project_dir, self.directory_isolation_path, symlinks=True)

        self.prepare_inventory()
        self.prepare_command()

        if self.execution_mode == ExecutionMode.ANSIBLE_PLAYBOOK and self.playbook is None:
            raise ConfigurationError("Runner playbook required when running ansible-playbook")
        elif self.execution_mode == ExecutionMode.ANSIBLE and self.module is None:
            raise ConfigurationError("Runner module required when running ansible")
        elif self.execution_mode == ExecutionMode.NONE:
            raise ConfigurationError("No executable for runner to run")

        self._handle_command_wrap()

        debug('env:')
        for k, v in sorted(self.env.items()):
            debug(f' {k}: {v}')
        if hasattr(self, 'command') and isinstance(self.command, list):
            debug(f"command: {' '.join(self.command)}")

    def prepare_inventory(self):
        """
        Prepares the inventory default under ``private_data_dir`` if it's not overridden by the constructor.
        """
        if self.containerized:
            self.inventory = '/runner/inventory/hosts'
            return

        if self.inventory is None:
            if os.path.exists(os.path.join(self.private_data_dir, "inventory")):
                self.inventory = os.path.join(self.private_data_dir, "inventory")

    def prepare_env(self):
        """
        Manages reading environment metadata files under ``private_data_dir`` and merging/updating
        with existing values so the :py:class:`ansible_runner.runner.Runner` object can read and use them easily
        """

        # setup common env settings
        super(RunnerConfig, self)._prepare_env()

        self.process_isolation_path = self.settings.get('process_isolation_path', self.process_isolation_path)
        self.process_isolation_hide_paths = self.settings.get('process_isolation_hide_paths', self.process_isolation_hide_paths)
        self.process_isolation_show_paths = self.settings.get('process_isolation_show_paths', self.process_isolation_show_paths)
        self.process_isolation_ro_paths = self.settings.get('process_isolation_ro_paths', self.process_isolation_ro_paths)
        self.directory_isolation_path = self.settings.get('directory_isolation_base_path', self.directory_isolation_path)
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

        if self.roles_path:
            if isinstance(self.roles_path, list):
                self.env['ANSIBLE_ROLES_PATH'] = ':'.join(self.roles_path)
            else:
                self.env['ANSIBLE_ROLES_PATH'] = self.roles_path

        self.env["RUNNER_OMIT_EVENTS"] = str(self.omit_event_data)
        self.env["RUNNER_ONLY_FAILED_EVENTS"] = str(self.only_failed_event_data)

    def prepare_command(self):
        try:
            cmdline_args = self.loader.load_file('args', string_types, encoding=None)

            if six.PY2 and isinstance(cmdline_args, text_type):
                cmdline_args = cmdline_args.encode('utf-8')
            self.command = shlex.split(cmdline_args)
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
            if self.cmdline_args:
                cmdline_args = self.cmdline_args
            else:
                cmdline_args = self.loader.load_file('env/cmdline', string_types, encoding=None)

            if six.PY2 and isinstance(cmdline_args, text_type):
                cmdline_args = cmdline_args.encode('utf-8')

            args = shlex.split(cmdline_args)
            exec_list.extend(args)
        except ConfigurationError:
            pass

        if self.inventory is None:
            pass
        elif isinstance(self.inventory, list):
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
            if self.containerized:
                extravars_path = '/runner/env/extravars'
            else:
                extravars_path = self.loader.abspath('env/extravars')
            exec_list.extend(['-e', '@{}'.format(extravars_path)])

        if self.extra_vars:
            if isinstance(self.extra_vars, dict) and self.extra_vars:
                extra_vars_list = []
                for k in self.extra_vars:
                    extra_vars_list.append("\"{}\":{}".format(k, json.dumps(self.extra_vars[k])))

                exec_list.extend(
                    [
                        '-e',
                        '{%s}' % ','.join(extra_vars_list)
                    ]
                )
            elif self.loader.isfile(self.extra_vars):
                exec_list.extend(['-e', '@{}'.format(self.loader.abspath(self.extra_vars))])

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

        register_for_cleanup(path)

        return path

    def wrap_args_for_sandbox(self, args):
        '''
        Wrap existing command line with bwrap to restrict access to:
         - self.process_isolation_path (generally, /tmp) (except for own /tmp files)
        '''
        cwd = os.path.realpath(self.cwd)
        self.process_isolation_path_actual = self.build_process_isolation_temp_dir()
        new_args = [self.process_isolation_executable or 'bwrap']

        new_args.extend([
            '--die-with-parent',
            '--unshare-pid',
            '--dev-bind', '/dev', 'dev',
            '--proc', '/proc',
            '--dir', '/tmp',
            '--ro-bind', '/bin', '/bin',
            '--ro-bind', '/etc', '/etc',
            '--ro-bind', '/usr', '/usr',
            '--ro-bind', '/opt', '/opt',
            '--symlink', 'usr/lib64', '/lib64',
        ])

        for path in sorted(set(self.process_isolation_hide_paths or [])):
            if not os.path.exists(path):
                logger.debug('hide path not found: {0}'.format(path))
                continue
            path = os.path.realpath(path)
            if os.path.isdir(path):
                new_path = tempfile.mkdtemp(dir=self.process_isolation_path_actual)
                os.chmod(new_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            else:
                handle, new_path = tempfile.mkstemp(dir=self.process_isolation_path_actual)
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
            new_args.extend(['--ro-bind', '{0}'.format(path), '{0}'.format(path)])

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
                new_args.extend(['--chdir', os.path.realpath(self.project_dir)])
        elif self.execution_mode == ExecutionMode.ANSIBLE:
            # ad-hoc runs should cwd to the root of the private data dir
            new_args.extend(['--chdir', os.path.realpath(self.private_data_dir)])

        new_args.extend(args)
        return new_args

    def _handle_command_wrap(self):
        # wrap args for ssh-agent
        if self.ssh_key_data:
            debug('ssh-agent agrs added')
            self.command = self.wrap_args_with_ssh_agent(self.command, self.ssh_key_path)

        if self.sandboxed:
            debug('sandbox enabled')
            self.command = self.wrap_args_for_sandbox(self.command)
        else:
            debug('sandbox disabled')

        if self.containerized:
            debug('containerization enabled')
            # container volume mount is handled explicitly for run API's
            # using 'container_volume_mounts' arguments
            base_execution_mode = BaseExecutionMode.NONE
            self.command = self.wrap_args_for_containerization(self.command, base_execution_mode, self.cmdline_args)
        else:
            debug('containerization disabled')
