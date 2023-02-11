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
import pexpect
import re
import stat
import tempfile
import shutil

from base64 import b64encode
from uuid import uuid4
try:
    from collections.abc import Mapping
except ImportError:
    from collections import Mapping

from six import iteritems, string_types

from ansible_runner import defaults
from ansible_runner.output import debug
from ansible_runner.exceptions import ConfigurationError
from ansible_runner.defaults import registry_auth_prefix
from ansible_runner.loader import ArtifactLoader
from ansible_runner.utils import (
    get_callback_dir,
    open_fifo_write,
    args2cmdline,
    sanitize_container_name,
    cli_mounts,
    register_for_cleanup,
)

logger = logging.getLogger('ansible-runner')


class BaseExecutionMode():
    NONE = 0
    # run ansible commands either locally or within EE
    ANSIBLE_COMMANDS = 1
    # execute generic commands
    GENERIC_COMMANDS = 2


class BaseConfig(object):

    def __init__(self,
                 private_data_dir=None, host_cwd=None, envvars=None, passwords=None, settings=None,
                 project_dir=None, artifact_dir=None, fact_cache_type='jsonfile', fact_cache=None,
                 process_isolation=False, process_isolation_executable=None,
                 container_image=None, container_volume_mounts=None, container_options=None, container_workdir=None, container_auth_data=None,
                 ident=None, rotate_artifacts=0, timeout=None, ssh_key=None, quiet=False, json_mode=False,
                 check_job_event_data=False, suppress_env_files=False, keepalive_seconds=None):
        # common params
        self.host_cwd = host_cwd
        self.envvars = envvars
        self.ssh_key_data = ssh_key

        # container params
        self.process_isolation = process_isolation
        self.process_isolation_executable = process_isolation_executable or defaults.default_process_isolation_executable
        self.container_image = container_image or defaults.default_container_image
        self.container_volume_mounts = container_volume_mounts
        self.container_workdir = container_workdir
        self.container_auth_data = container_auth_data
        self.registry_auth_path = None
        self.container_name = None  # like other properties, not accurate until prepare is called
        self.container_options = container_options
        self._volume_mount_paths = []

        # runner params
        self.private_data_dir = private_data_dir
        self.rotate_artifacts = rotate_artifacts
        self.quiet = quiet
        self.json_mode = json_mode
        self.passwords = passwords
        self.settings = settings
        self.timeout = timeout
        self.check_job_event_data = check_job_event_data
        self.suppress_env_files = suppress_env_files
        # ignore this for now since it's worker-specific and would just trip up old runners
        # self.keepalive_seconds = keepalive_seconds

        # setup initial environment
        if private_data_dir:
            self.private_data_dir = os.path.abspath(private_data_dir)
            # Note that os.makedirs, exist_ok=True is dangerous.  If there's a directory writable
            # by someone other than the user anywhere in the path to be created, an attacker can
            # attempt to compromise the directories via a race.
            os.makedirs(self.private_data_dir, exist_ok=True, mode=0o700)
        else:
            self.private_data_dir = tempfile.mkdtemp(prefix=defaults.AUTO_CREATE_NAMING, dir=defaults.AUTO_CREATE_DIR)

        if artifact_dir is None:
            artifact_dir = os.path.join(self.private_data_dir, 'artifacts')
        else:
            artifact_dir = os.path.abspath(artifact_dir)

        if ident is None:
            self.ident = str(uuid4())
        else:
            self.ident = ident

        self.artifact_dir = os.path.join(artifact_dir, "{}".format(self.ident))

        if not project_dir:
            self.project_dir = os.path.join(self.private_data_dir, 'project')
        else:
            self.project_dir = project_dir

        self.rotate_artifacts = rotate_artifacts
        self.fact_cache_type = fact_cache_type
        self.fact_cache = os.path.join(self.artifact_dir, fact_cache or 'fact_cache') if self.fact_cache_type == 'jsonfile' else None

        self.loader = ArtifactLoader(self.private_data_dir)

        if self.host_cwd:
            self.host_cwd = os.path.abspath(self.host_cwd)
            self.cwd = self.host_cwd
        else:
            self.cwd = os.getcwd()

        os.makedirs(self.artifact_dir, exist_ok=True, mode=0o700)

    _CONTAINER_ENGINES = ('docker', 'podman')

    @property
    def containerized(self):
        return self.process_isolation and self.process_isolation_executable in self._CONTAINER_ENGINES

    def _prepare_env(self, runner_mode='pexpect'):
        """
        Manages reading environment metadata files under ``private_data_dir`` and merging/updating
        with existing values so the :py:class:`ansible_runner.runner.Runner` object can read and use them easily
        """
        self.runner_mode = runner_mode
        try:
            if self.settings and isinstance(self.settings, dict):
                self.settings.update(self.loader.load_file('env/settings', Mapping))
            else:
                self.settings = self.loader.load_file('env/settings', Mapping)
        except ConfigurationError:
            debug("Not loading settings")
            self.settings = dict()

        if self.runner_mode == 'pexpect':
            try:
                if self.passwords and isinstance(self.passwords, dict):
                    self.passwords.update(self.loader.load_file('env/passwords', Mapping))
                else:
                    self.passwords = self.passwords or self.loader.load_file('env/passwords', Mapping)
            except ConfigurationError:
                debug('Not loading passwords')

            self.expect_passwords = dict()
            try:
                if self.passwords:
                    self.expect_passwords = {
                        re.compile(pattern, re.M): password
                        for pattern, password in iteritems(self.passwords)
                    }
            except Exception as e:
                debug('Failed to compile RE from passwords: {}'.format(e))

            self.expect_passwords[pexpect.TIMEOUT] = None
            self.expect_passwords[pexpect.EOF] = None

            self.pexpect_timeout = self.settings.get('pexpect_timeout', 5)
            self.pexpect_use_poll = self.settings.get('pexpect_use_poll', True)
            self.idle_timeout = self.settings.get('idle_timeout', None)

            if self.timeout:
                self.job_timeout = int(self.timeout)
            else:
                self.job_timeout = self.settings.get('job_timeout', None)

        elif self.runner_mode == 'subprocess':
            if self.timeout:
                self.subprocess_timeout = int(self.timeout)
            else:
                self.subprocess_timeout = self.settings.get('subprocess_timeout', None)

        self.process_isolation = self.settings.get('process_isolation', self.process_isolation)
        self.process_isolation_executable = self.settings.get('process_isolation_executable', self.process_isolation_executable)

        self.container_image = self.settings.get('container_image', self.container_image)
        self.container_volume_mounts = self.settings.get('container_volume_mounts', self.container_volume_mounts)
        self.container_options = self.settings.get('container_options', self.container_options)
        self.container_auth_data = self.settings.get('container_auth_data', self.container_auth_data)

        if self.containerized:
            self.container_name = "ansible_runner_{}".format(sanitize_container_name(self.ident))
            self.env = {}

            if self.process_isolation_executable == 'podman':
                # A kernel bug in RHEL < 8.5 causes podman to use the fuse-overlayfs driver. This results in errors when
                # trying to set extended file attributes. Setting this environment variable allows modules to take advantage
                # of a fallback to work around this bug when failures are encountered.
                #
                # See the following for more information:
                #    https://github.com/ansible/ansible/pull/73282
                #    https://github.com/ansible/ansible/issues/73310
                #    https://issues.redhat.com/browse/AAP-476
                self.env['ANSIBLE_UNSAFE_WRITES'] = '1'

            artifact_dir = os.path.join("/runner/artifacts", "{}".format(self.ident))
            self.env['AWX_ISOLATED_DATA_DIR'] = artifact_dir
            if self.fact_cache_type == 'jsonfile':
                self.env['ANSIBLE_CACHE_PLUGIN_CONNECTION'] = os.path.join(artifact_dir, 'fact_cache')

        else:
            # seed env with existing shell env
            self.env = os.environ.copy()

        if self.envvars and isinstance(self.envvars, dict):
            self.env.update(self.envvars)

        try:
            envvars = self.loader.load_file('env/envvars', Mapping)
            if envvars:
                self.env.update(envvars)
        except ConfigurationError:
            debug("Not loading environment vars")
            # Still need to pass default environment to pexpect

        try:
            if self.ssh_key_data is None:
                self.ssh_key_data = self.loader.load_file('env/ssh_key', string_types)
        except ConfigurationError:
            debug("Not loading ssh key")
            self.ssh_key_data = None

        # write the SSH key data into a fifo read by ssh-agent
        if self.ssh_key_data:
            self.ssh_key_path = os.path.join(self.artifact_dir, 'ssh_key_data')
            open_fifo_write(self.ssh_key_path, self.ssh_key_data)

        self.suppress_output_file = self.settings.get('suppress_output_file', False)
        self.suppress_ansible_output = self.settings.get('suppress_ansible_output', self.quiet)

        if 'fact_cache' in self.settings:
            if 'fact_cache_type' in self.settings:
                if self.settings['fact_cache_type'] == 'jsonfile':
                    self.fact_cache = os.path.join(self.artifact_dir, self.settings['fact_cache'])
            else:
                self.fact_cache = os.path.join(self.artifact_dir, self.settings['fact_cache'])

        # Use local callback directory
        if self.containerized:
            # when containerized, copy the callback dir to $private_data_dir/artifacts/<job_id>/callback
            # then append to env['ANSIBLE_CALLBACK_PLUGINS'] with the copied location.
            callback_dir = os.path.join(self.artifact_dir, 'callback')
            # if callback dir already exists (on repeat execution with the same ident), remove it first.
            if os.path.exists(callback_dir):
                shutil.rmtree(callback_dir)
            shutil.copytree(get_callback_dir(), callback_dir)

            container_callback_dir = os.path.join("/runner/artifacts", "{}".format(self.ident), "callback")
            self.env['ANSIBLE_CALLBACK_PLUGINS'] = ':'.join(filter(None, (self.env.get('ANSIBLE_CALLBACK_PLUGINS'), container_callback_dir)))
        else:
            callback_dir = self.env.get('AWX_LIB_DIRECTORY', os.getenv('AWX_LIB_DIRECTORY'))
            if callback_dir is None:
                callback_dir = get_callback_dir()
            self.env['ANSIBLE_CALLBACK_PLUGINS'] = ':'.join(filter(None, (self.env.get('ANSIBLE_CALLBACK_PLUGINS'), callback_dir)))

        # this is an adhoc command if the module is specified, TODO: combine with logic in RunnerConfig class
        is_adhoc = bool((getattr(self, 'binary', None) is None) and (getattr(self, 'module', None) is not None))

        if self.env.get('ANSIBLE_STDOUT_CALLBACK'):
            self.env['ORIGINAL_STDOUT_CALLBACK'] = self.env.get('ANSIBLE_STDOUT_CALLBACK')

        if is_adhoc:
            # force loading awx_display stdout callback for adhoc commands
            self.env["ANSIBLE_LOAD_CALLBACK_PLUGINS"] = '1'
            if 'AD_HOC_COMMAND_ID' not in self.env:
                self.env['AD_HOC_COMMAND_ID'] = '1'

        self.env['ANSIBLE_STDOUT_CALLBACK'] = 'awx_display'

        self.env['ANSIBLE_RETRY_FILES_ENABLED'] = 'False'
        if 'ANSIBLE_HOST_KEY_CHECKING' not in self.env:
            self.env['ANSIBLE_HOST_KEY_CHECKING'] = 'False'
        if not self.containerized:
            self.env['AWX_ISOLATED_DATA_DIR'] = self.artifact_dir

        if self.fact_cache_type == 'jsonfile':
            self.env['ANSIBLE_CACHE_PLUGIN'] = 'jsonfile'
            if not self.containerized:
                self.env['ANSIBLE_CACHE_PLUGIN_CONNECTION'] = self.fact_cache

        # Pexpect will error with non-string envvars types, so we ensure string types
        self.env = {str(k): str(v) for k, v in self.env.items()}

        debug('env:')
        for k, v in sorted(self.env.items()):
            debug(f' {k}: {v}')

    def _handle_command_wrap(self, execution_mode, cmdline_args):
        if self.ssh_key_data:
            logger.debug('ssh key data added')
            self.command = self.wrap_args_with_ssh_agent(self.command, self.ssh_key_path)

        if self.containerized:
            logger.debug('containerization enabled')
            self.command = self.wrap_args_for_containerization(self.command, execution_mode, cmdline_args)
        else:
            logger.debug('containerization disabled')

        if hasattr(self, 'command') and isinstance(self.command, list):
            logger.debug(f"command: {' '.join(self.command)}")

    def _ensure_path_safe_to_mount(self, path):
        if os.path.isfile(path):
            path = os.path.dirname(path)
        if os.path.join(path, "") in ('/', '/home/', '/usr/'):
            raise ConfigurationError("When using containerized execution, cannot mount '/' or '/home' or '/usr'")

    def _get_playbook_path(self, cmdline_args):
        _playbook = ""
        _book_keeping_copy = cmdline_args.copy()
        for arg in cmdline_args:
            if arg in ['-i', '--inventory', '--inventory-file']:
                _book_keeping_copy_inventory_index = _book_keeping_copy.index(arg)
                _book_keeping_copy.pop(_book_keeping_copy_inventory_index)
                try:
                    _book_keeping_copy.pop(_book_keeping_copy_inventory_index)
                except IndexError:
                    # invalid command, pass through for execution
                    # to return correct error from ansible-core
                    return None

        if len(_book_keeping_copy) == 1:
            # it's probably safe to assume this is the playbook
            _playbook = _book_keeping_copy[0]
        elif _book_keeping_copy[0][0] != '-':
            # this should be the playbook, it's the only "naked" arg
            _playbook = _book_keeping_copy[0]
        else:
            # parse everything beyond the first arg because we checked that
            # in the previous case already
            for arg in _book_keeping_copy[1:]:
                if arg[0] == '-':
                    continue
                elif _book_keeping_copy[(_book_keeping_copy.index(arg) - 1)][0] != '-':
                    _playbook = arg
                    break

        return _playbook

    def _update_volume_mount_paths(
        self, args_list, src_mount_path, dst_mount_path=None, labels=None
    ):

        if src_mount_path is None or not os.path.exists(src_mount_path):
            logger.debug("Source volume mount path does not exit {0}".format(src_mount_path))
            return

        # ensure source is abs
        src_path = os.path.abspath(os.path.expanduser(os.path.expandvars(src_mount_path)))

        # set dest src (if None) relative to workdir(not absolute) or provided
        if dst_mount_path is None:
            dst_path = src_path
        elif self.container_workdir and not os.path.isabs(dst_mount_path):
            dst_path = os.path.abspath(
                os.path.expanduser(
                    os.path.expandvars(os.path.join(self.container_workdir, dst_mount_path))
                )
            )
        else:
            dst_path = os.path.abspath(os.path.expanduser(os.path.expandvars(dst_mount_path)))

        # ensure each is a directory not file, use src for dest
        # because dest doesn't exist locally
        src_dir = src_path if os.path.isdir(src_path) else os.path.dirname(src_path)
        dst_dir = dst_path if os.path.isdir(src_path) else os.path.dirname(dst_path)

        # always ensure a trailing slash
        src_dir = os.path.join(src_dir, "")
        dst_dir = os.path.join(dst_dir, "")

        # ensure the src and dest are safe mount points
        # after stripping off the file and resolving
        self._ensure_path_safe_to_mount(src_dir)
        self._ensure_path_safe_to_mount(dst_dir)

        # format the src dest str
        volume_mount_path = "{}:{}".format(src_dir, dst_dir)

        # add labels as needed
        if labels:
            if not labels.startswith(":"):
                volume_mount_path += ":"
            volume_mount_path += labels

        # check if mount path already added in args list
        if volume_mount_path not in args_list:
            args_list.extend(["-v", volume_mount_path])

    def _handle_ansible_cmd_options_bind_mounts(self, args_list, cmdline_args):
        inventory_file_options = ['-i', '--inventory', '--inventory-file']
        vault_file_options = ['--vault-password-file', '--vault-pass-file']
        private_key_file_options = ['--private-key', '--key-file']

        optional_mount_args = inventory_file_options + vault_file_options + private_key_file_options

        if not cmdline_args:
            return

        if '-h' in cmdline_args or '--help' in cmdline_args:
            return

        for value in self.command:
            if 'ansible-playbook' in value:
                playbook_file_path = self._get_playbook_path(cmdline_args)
                if playbook_file_path:
                    self._update_volume_mount_paths(args_list, playbook_file_path)
                    break

        cmdline_args_copy = cmdline_args.copy()
        optional_arg_paths = []
        for arg in cmdline_args:

            if arg not in optional_mount_args:
                continue

            optional_arg_index = cmdline_args_copy.index(arg)
            optional_arg_paths.append(cmdline_args[optional_arg_index + 1])
            cmdline_args_copy.pop(optional_arg_index)
            try:
                optional_arg_value = cmdline_args_copy.pop(optional_arg_index)
            except IndexError:
                # invalid command, pass through for execution
                # to return valid error from ansible-core
                return

            if arg in inventory_file_options and optional_arg_value.endswith(','):
                # comma separated host list provided as value
                continue

            self._update_volume_mount_paths(args_list, optional_arg_value)

    def wrap_args_for_containerization(self, args, execution_mode, cmdline_args):
        new_args = [self.process_isolation_executable]
        new_args.extend(['run', '--rm'])

        if self.runner_mode == 'pexpect' or hasattr(self, 'input_fd') and self.input_fd is not None:
            new_args.extend(['--tty'])

        new_args.append('--interactive')

        if self.container_workdir:
            workdir = self.container_workdir
        elif self.host_cwd is not None and os.path.exists(self.host_cwd):
            # mount current host working diretory if passed and exist
            self._ensure_path_safe_to_mount(self.host_cwd)
            self._update_volume_mount_paths(new_args, self.host_cwd)
            workdir = self.host_cwd
        else:
            workdir = "/runner/project"

        self.cwd = workdir
        new_args.extend(["--workdir", workdir])

        # For run() and run_async() API value of base execution_mode is 'BaseExecutionMode.NONE'
        # and the container volume mounts are handled separately using 'container_volume_mounts'
        # hence ignore additional mount here
        if execution_mode != BaseExecutionMode.NONE:
            if execution_mode == BaseExecutionMode.ANSIBLE_COMMANDS:
                self._handle_ansible_cmd_options_bind_mounts(new_args, cmdline_args)

            # Handle automounts for .ssh config
            self._handle_automounts(new_args)

            if 'podman' in self.process_isolation_executable:
                # container namespace stuff
                new_args.extend(["--group-add=root"])
                new_args.extend(["--ipc=host"])

            self._ensure_path_safe_to_mount(self.private_data_dir)
            # Relative paths are mounted relative to /runner/project
            for subdir in ('project', 'artifacts'):
                subdir_path = os.path.join(self.private_data_dir, subdir)
                if not os.path.exists(subdir_path):
                    os.mkdir(subdir_path, 0o700)

            # runtime commands need artifacts mounted to output data
            self._update_volume_mount_paths(new_args,
                                            "{}/artifacts".format(self.private_data_dir),
                                            dst_mount_path="/runner/artifacts",
                                            labels=":Z")

        else:
            subdir_path = os.path.join(self.private_data_dir, 'artifacts')
            if not os.path.exists(subdir_path):
                os.mkdir(subdir_path, 0o700)

        # Mount the entire private_data_dir
        # custom show paths inside private_data_dir do not make sense
        self._update_volume_mount_paths(new_args, "{}".format(self.private_data_dir), dst_mount_path="/runner", labels=":Z")

        if self.container_auth_data:
            # Pull in the necessary registry auth info, if there is a container cred
            self.registry_auth_path, registry_auth_conf_file = self._generate_container_auth_dir(self.container_auth_data)
            if 'podman' in self.process_isolation_executable:
                new_args.extend(["--authfile={}".format(self.registry_auth_path)])
            else:
                docker_idx = new_args.index(self.process_isolation_executable)
                new_args.insert(docker_idx + 1, "--config={}".format(self.registry_auth_path))
            if registry_auth_conf_file is not None:
                # Podman >= 3.1.0
                self.env['CONTAINERS_REGISTRIES_CONF'] = registry_auth_conf_file
                # Podman < 3.1.0
                self.env['REGISTRIES_CONFIG_PATH'] = registry_auth_conf_file

        if self.container_volume_mounts:
            for mapping in self.container_volume_mounts:
                volume_mounts = mapping.split(':', 2)
                self._ensure_path_safe_to_mount(volume_mounts[0])
                labels = None
                if len(volume_mounts) == 3:
                    labels = ":%s" % volume_mounts[2]
                self._update_volume_mount_paths(new_args, volume_mounts[0], dst_mount_path=volume_mounts[1], labels=labels)

        # Reference the file with list of keys to pass into container
        # this file will be written in ansible_runner.runner
        env_file_host = os.path.join(self.artifact_dir, 'env.list')
        new_args.extend(['--env-file', env_file_host])

        if 'podman' in self.process_isolation_executable:
            # docker doesnt support this option
            new_args.extend(['--quiet'])

        if 'docker' in self.process_isolation_executable:
            new_args.extend([f'--user={os.getuid()}'])

        new_args.extend(['--name', self.container_name])

        if self.container_options:
            new_args.extend(self.container_options)

        new_args.extend([self.container_image])
        new_args.extend(args)
        logger.debug(f"container engine invocation: {' '.join(new_args)}")
        return new_args

    def _generate_container_auth_dir(self, auth_data):
        host = auth_data.get('host')
        token = "{}:{}".format(auth_data.get('username'), auth_data.get('password'))
        encoded_container_auth_data = {'auths': {host: {'auth': b64encode(token.encode('UTF-8')).decode('UTF-8')}}}
        # Create a new temp file with container auth data
        path = tempfile.mkdtemp(prefix='%s%s_' % (registry_auth_prefix, self.ident))
        register_for_cleanup(path)

        if self.process_isolation_executable == 'docker':
            auth_filename = 'config.json'
        else:
            auth_filename = 'auth.json'
        registry_auth_path = os.path.join(path, auth_filename)
        with open(registry_auth_path, 'w') as authfile:
            os.chmod(authfile.name, stat.S_IRUSR | stat.S_IWUSR)
            authfile.write(json.dumps(encoded_container_auth_data, indent=4))

        registries_conf_path = None
        if auth_data.get('verify_ssl', True) is False:
            registries_conf_path = os.path.join(path, 'registries.conf')

            with open(registries_conf_path, 'w') as registries_conf:
                os.chmod(registries_conf.name, stat.S_IRUSR | stat.S_IWUSR)

                lines = [
                    '[[registry]]',
                    'location = "{}"'.format(host),
                    'insecure = true',
                ]

                registries_conf.write('\n'.join(lines))

        auth_path = authfile.name
        if self.process_isolation_executable == 'docker':
            auth_path = path  # docker expects to be passed directory
        return (auth_path, registries_conf_path)

    def wrap_args_with_ssh_agent(self, args, ssh_key_path, ssh_auth_sock=None, silence_ssh_add=False):
        """
        Given an existing command line and parameterization this will return the same command line wrapped with the
        necessary calls to ``ssh-agent``
        """
        if self.containerized:
            artifact_dir = os.path.join("/runner/artifacts", "{}".format(self.ident))
            ssh_key_path = os.path.join(artifact_dir, "ssh_key_data")

        if ssh_key_path:
            ssh_add_command = args2cmdline('ssh-add', ssh_key_path)
            if silence_ssh_add:
                ssh_add_command = ' '.join([ssh_add_command, '2>/dev/null'])
            ssh_key_cleanup_command = 'rm -f {}'.format(ssh_key_path)
            # The trap ensures the fifo is cleaned up even if the call to ssh-add fails.
            # This prevents getting into certain scenarios where subsequent reads will
            # hang forever.
            cmd = ' && '.join([args2cmdline('trap', ssh_key_cleanup_command, 'EXIT'),
                               ssh_add_command,
                               ssh_key_cleanup_command,
                               args2cmdline(*args)])
            args = ['ssh-agent']
            if ssh_auth_sock:
                args.extend(['-a', ssh_auth_sock])
            args.extend(['sh', '-c', cmd])
        return args

    def _handle_automounts(self, new_args):
        for cli_automount in cli_mounts():
            for env in cli_automount['ENVS']:
                if env in os.environ:
                    dest_path = os.environ[env]

                    if os.path.exists(os.environ[env]):
                        if os.environ[env].startswith(os.environ['HOME']):
                            dest_path = '/home/runner/{}'.format(os.environ[env].lstrip(os.environ['HOME']))
                        elif os.environ[env].startswith('~'):
                            dest_path = '/home/runner/{}'.format(os.environ[env].lstrip('~/'))
                        else:
                            dest_path = os.environ[env]

                        self._update_volume_mount_paths(new_args, os.environ[env], dst_mount_path=dest_path)

                    new_args.extend(["-e", "{}={}".format(env, dest_path)])

            for paths in cli_automount['PATHS']:
                if os.path.exists(paths['src']):
                    self._update_volume_mount_paths(new_args, paths['src'], dst_mount_path=paths['dest'])
