import os
import re
import yaml
import pipes
import thread
import pexpect
from uuid import uuid4

from .exceptions import ConfigurationError


class RunnerConfig(object):

    def __init__(self, base_dir, playbook,
                 ident=uuid4(), inventory=None, limit=None,
                 module=None, module_args=None):
        self.base_dir = os.path.abspath(base_dir)
        self.ident = ident
        self.playbook = playbook
        self.inventory = inventory
        self.limit = limit
        self.module = module
        self.module_args = module_args
        if self.ident is None:
            self.artifact_dir = os.path.join(self.base_dir, "artifacts")
        else:
            self.artifact_dir = os.path.join(self.base_dir, "artifacts", "{}".format(self.ident))

    def prepare_inventory(self):
        if self.inventory is None:
            self.inventory  = os.path.join(self.base_dir, "inventory")

    def prepare_env(self):
        try:
            with open(os.path.join(self.base_dir, "env", "passwords"), 'r') as f:
                self.expect_passwords = {
                    re.compile(pattern, re.M): password
                    for pattern, password in yaml.load(f.read()).items()
                }
        except Exception:
            # TODO: logging
            print("Not loading passwords")
            self.expect_passwords = dict()
        self.expect_passwords[pexpect.TIMEOUT] = None
        self.expect_passwords[pexpect.EOF] = None

        try:
            with open(os.path.join(self.base_dir, "env", "envvars"), 'r') as f:
                self.env = yaml.load(f.read())
        except Exception:
            print("Not loading environment vars")
            self.env = dict()

        try:
            with open(os.path.join(self.base_dir, "env", "extravars"), 'r') as f:
                self.extra_vars = yaml.load(f.read())
        except Exception:
            print("Not loading extra vars")
            self.extra_vars = dict()

        try:
            with open(os.path.join(self.base_dir, "env", "settings"), 'r') as f:
                self.settings = yaml.load(f.read())
        except Exception:
            print("Not loading settings")
            self.settings = dict()

        try:
            with open(os.path.join(self.base_dir, "env", "ssh_key"), 'r') as f:
                self.ssh_key_data = f.read()
        except Exception:
            print("Not loading ssh key")
            self.ssh_key_data = None

        # write the SSH key data into a fifo read by ssh-agent
        if self.ssh_key_data:
            self.ssh_key_path = os.path.join(self.artifact_dir, 'ssh_key_data')
            self.ssh_auth_sock = os.path.join(self.artifact_dir, 'ssh_auth.sock')
            self.open_fifo_write(self.ssh_key_path, self.ssh_key_data)
            self.command = self.wrap_args_with_ssh_agent(self.command, self.ssh_key_path, self.ssh_auth_sock)

        self.idle_timeout = self.settings.get('idle_timeout', 120)
        self.job_timeout = self.settings.get('job_timeout', 120)
        self.pexpect_timeout = self.settings.get('pexpect_timeout', 5)

        if 'AD_HOC_COMMAND_ID' in self.env:
            self.cwd = self.base_dir
        else:
            self.cwd = os.path.join(self.base_dir, 'project')

    def prepare_command(self):
        if os.path.exists(os.path.join(self.base_dir, 'args')):
            with open(os.path.join(self.base_dir, 'args'), 'r') as args:
                self.command = yaml.load(args)
        else:
            self.command = self.generate_ansible_command()

    def prepare(self):
        if self.base_dir is None:
            raise ConfigurationError("Runner Base Directory is not defined")
        if self.playbook is None: # TODO: ad-hoc mode, module and args
            raise ConfigurationError("Runner playbook is not defined")
        if not os.path.exists(self.artifact_dir):
            os.makedirs(self.artifact_dir)

        self.prepare_inventory()
        self.prepare_env()
        self.prepare_command()
        
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
        self.env['AWX_ISOLATED_DATA_DIR'] = self.artifact_dir
        self.env['PYTHONPATH'] = self.env.get('PYTHONPATH', '') + callback_dir + ':'


    def generate_ansible_command(self):
        if self.module is not None:
            base_command = 'ansible'
        else:
            base_command = 'ansible-playbook'
        exec_list = [base_command]
        exec_list.append("-i")
        exec_list.append(self.inventory)
        if self.limit is not None:
            exec_list.append("--limit")
            exec_list.append(self.limit)
        if self.extra_vars:
            for evar in self.extra_vars:
                exec_list.append("-e")
                exec_list.append("{}={}".format(evar, self.extra_vars[evar]))
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
        os.mkfifo(path, 0o644)
        thread.start_new_thread(lambda p, d: open(p, 'w').write(d), (path, data))


    def args2cmdline(*args):
        # TODO: switch to utility function
        return ' '.join([pipes.quote(a) for a in args])
