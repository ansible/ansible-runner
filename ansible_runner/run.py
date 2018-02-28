#! /usr/bin/env python

import argparse
import codecs
import collections
import logging
import json
import yaml
import os
import stat
import pipes
import re
import signal
import sys
import thread
import time
import pkg_resources
from uuid import uuid4

import pexpect
import psutil


logger = logging.getLogger('ansible_runner.run')


class OutputWriter(object):

    def __init__(self, handle):
        self.handle = handle

    def flush(self):
        pass

    def write(self, data):
        sys.stdout.write(data)
        self.handle.write(data)

    def close(self):
        sys.stdout("Process Finished")
        self.handle.close()


def args2cmdline(*args):
    return ' '.join([pipes.quote(a) for a in args])


def wrap_args_with_ssh_agent(args, ssh_key_path, ssh_auth_sock=None, silence_ssh_add=False):
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


def generate_ansible_command(hosts_or_inv_path, limit=None, playbook=None,
                             extra_vars=[], module=None, module_args=None):
    base_command = os.getenv("RUNNER_BASE_COMMAND", "ansible-playbook")
    exec_list = [base_command]
    exec_list.append("-i")
    exec_list.append(hosts_or_inv_path)
    if limit is not None:
        exec_list.append("--limit")
        exec_list.append(limit)
    if extra_vars:
        for evar in extra_vars:
            exec_list.append("-e")
            exec_list.append("{}={}".format(evar, extra_vars[evar]))
    # Other parameters
    if base_command.endswith('ansible-playbook'):
        exec_list.append(playbook)
    elif base_command == 'ansible':
        exec_list.append("-m")
        exec_list.append(module)
        if module_args is not None:
            exec_list.append("-a")
            exec_list.append(module_args)
    return exec_list


def open_fifo_write(path, data):
    '''open_fifo_write opens the fifo named pipe in a new thread.
    This blocks the thread until an external process (such as ssh-agent)
    reads data from the pipe.
    '''
    os.mkfifo(path, 0600)
    thread.start_new_thread(lambda p, d: open(p, 'w').write(d), (path, data))


def run_pexpect(args, cwd, env, logfile,
                cancelled_callback=None, expect_passwords={},
                extra_update_fields=None, idle_timeout=None, job_timeout=0,
                pexpect_timeout=5, proot_cmd='bwrap'):
    '''
    Run the given command using pexpect to capture output and provide
    passwords when requested.

    :param args:                a list of `subprocess.call`-style arguments
                                representing a subprocess e.g., ['ls', '-la']
    :param cwd:                 the directory in which the subprocess should
                                run
    :param env:                 a dict containing environment variables for the
                                subprocess, ala `os.environ`
    :param logfile:             a file-like object for capturing stdout
    :param cancelled_callback:  a callable - which returns `True` or `False`
                                - signifying if the job has been prematurely
                                  cancelled
    :param expect_passwords:    a dict of regular expression password prompts
                                to input values, i.e., {r'Password:\s*?$':
                                'some_password'}
    :param extra_update_fields: a dict used to specify DB fields which should
                                be updated on the underlying model
                                object after execution completes
    :param idle_timeout         a timeout (in seconds); if new output is not
                                sent to stdout in this interval, the process
                                will be terminated
    :param job_timeout          a timeout (in seconds); if the total job runtime
                                exceeds this, the process will be killed
    :param pexpect_timeout      a timeout (in seconds) to wait on
                                `pexpect.spawn().expect()` calls
    :param proot_cmd            the command used to isolate processes, `bwrap`

    Returns a tuple (status, return_code) i.e., `('successful', 0)`
    '''
    expect_passwords[pexpect.TIMEOUT] = None
    expect_passwords[pexpect.EOF] = None

    if not isinstance(expect_passwords, collections.OrderedDict):
        # We iterate over `expect_passwords.keys()` and
        # `expect_passwords.values()` separately to map matched inputs to
        # patterns and choose the proper string to send to the subprocess;
        # enforce usage of an OrderedDict so that the ordering of elements in
        # `keys()` matches `values()`.
        expect_passwords = collections.OrderedDict(expect_passwords)
    password_patterns = expect_passwords.keys()
    password_values = expect_passwords.values()

    child = pexpect.spawn(
        args[0], args[1:], cwd=cwd, env=env, ignore_sighup=True,
        encoding='utf-8', echo=False,
    )
    child.logfile_read = logfile
    canceled = False
    timed_out = False
    errored = False
    last_stdout_update = time.time()

    job_start = time.time()
    while child.isalive():
        result_id = child.expect(password_patterns, timeout=pexpect_timeout, searchwindowsize=100)
        password = password_values[result_id]
        if password is not None:
            child.sendline(password)
            last_stdout_update = time.time()
        if cancelled_callback:
            try:
                canceled = cancelled_callback()
            except Exception:
                logger.exception('Could not check cancel callback - canceling immediately')
                if isinstance(extra_update_fields, dict):
                    extra_update_fields['job_explanation'] = "System error during job execution, check system logs"
                errored = True
        else:
            canceled = False
        if not canceled and job_timeout != 0 and (time.time() - job_start) > job_timeout:
            timed_out = True
            if isinstance(extra_update_fields, dict):
                extra_update_fields['job_explanation'] = "Job terminated due to timeout"
        if canceled or timed_out or errored:
            handle_termination(child.pid, child.args, proot_cmd, is_cancel=canceled)
        if idle_timeout and (time.time() - last_stdout_update) > idle_timeout:
            child.close(True)
            canceled = True
    if errored:
        return 'error', child.exitstatus
    elif canceled:
        return 'canceled', child.exitstatus
    elif child.exitstatus == 0 and not timed_out:
        return 'successful', child.exitstatus
    else:
        return 'failed', child.exitstatus


def run_isolated_job(private_data_dir, logfile=sys.stdout,
                     inventory_hosts=None, limit=None, playbook=None,
                     module=None, module_args=None, artifact_dir=None):
    '''
    Launch `ansible-playbook`, executing a job packaged by
    `build_isolated_job_data`.

    :param private_data_dir:  an absolute path on the local file system where
                              job metadata exists (i.e.,
                              `/tmp/ansible_awx_xyz/`)
    :param logfile:           a file-like object for capturing stdout

    Returns a tuple (status, return_code) i.e., `('successful', 0)`
    '''

    try:
        with open(os.path.join(private_data_dir, "env", "passwords"), 'r') as f:
            expect_passwords = {
                re.compile(pattern, re.M): password
                for pattern, password in yaml.load(f.read()).items()
            }
    except Exception:
        print("Not loading passwords")
        expect_passwords = dict()

    try:
        with open(os.path.join(private_data_dir, "env", "envvars"), 'r') as f:
            env = yaml.load(f.read())
    except Exception:
        print("Not loading environment vars")
        env = dict()

    try:
        with open(os.path.join(private_data_dir, "env", "extravars"), 'r') as f:
            extra_vars = yaml.load(f.read())
    except Exception:
        print("Not loading extra vars")
        extra_vars = dict()

    try:
        with open(os.path.join(private_data_dir, "env", "settings"), 'r') as f:
            settings = yaml.load(f.read())
    except Exception:
        print("Not loading settings")
        settings = dict()

    try:
        with open(os.path.join(private_data_dir, "env", "ssh_key"), 'r') as f:
            ssh_key_data = f.read()
    except Exception:
        print("Not loading ssh key")
        ssh_key_data = None

    if 'AD_HOC_COMMAND_ID' in env:
        cwd = private_data_dir
    else:
        cwd = os.path.join(private_data_dir, 'project')

    if os.path.exists(os.path.join(private_data_dir, 'args')):
        with open(os.path.join(private_data_dir, 'args'), 'r') as args:
            args = yaml.load(args)
    else:
        args = generate_ansible_command(inventory_hosts,
                                        limit=limit,
                                        playbook=playbook,
                                        extra_vars=extra_vars,
                                        module=module,
                                        module_args=module_args)


    # write the SSH key data into a fifo read by ssh-agent
    if ssh_key_data:
        ssh_key_path = os.path.join(artifact_dir, 'ssh_key_data')
        ssh_auth_sock = os.path.join(artifact_dir, 'ssh_auth.sock')
        open_fifo_write(ssh_key_path, ssh_key_data)
        args = wrap_args_with_ssh_agent(args, ssh_key_path, ssh_auth_sock)

    idle_timeout = settings.get('idle_timeout', 120)
    job_timeout = settings.get('job_timeout', 120)
    pexpect_timeout = settings.get('pexpect_timeout', 5)

    # Use local callback directory
    callback_dir = os.getenv('AWX_LIB_DIRECTORY')
    if callback_dir is None:
        callback_dir = os.path.join(os.path.dirname(__file__),
                                    "callbacks")
    env['ANSIBLE_CALLBACK_PLUGINS'] = callback_dir
    if 'AD_HOC_COMMAND_ID' in env:
        env['ANSIBLE_STDOUT_CALLBACK'] = 'minimal'
    else:
        env['ANSIBLE_STDOUT_CALLBACK'] = 'awx_display'
    env['AWX_ISOLATED_DATA_DIR'] = artifact_dir
    env['PYTHONPATH'] = env.get('PYTHONPATH', '') + callback_dir + ':'

    return run_pexpect(args, cwd, env, logfile,
                       expect_passwords=expect_passwords,
                       idle_timeout=idle_timeout,
                       job_timeout=job_timeout,
                       pexpect_timeout=pexpect_timeout)


def handle_termination(pid, args, proot_cmd, is_cancel=True):
    '''
    Terminate a subprocess spawned by `pexpect`.

    :param pid:       the process id of the running the job.
    :param args:      the args for the job, i.e., ['ansible-playbook', 'abc.yml']
    :param proot_cmd  the command used to isolate processes i.e., `bwrap`
    :param is_cancel: flag showing whether this termination is caused by
                      instance's cancel_flag.
    '''
    try:
        if proot_cmd in ' '.join(args):
            if not psutil:
                os.kill(pid, signal.SIGKILL)
            else:
                try:
                    main_proc = psutil.Process(pid=pid)
                    child_procs = main_proc.children(recursive=True)
                    for child_proc in child_procs:
                        os.kill(child_proc.pid, signal.SIGKILL)
                    os.kill(main_proc.pid, signal.SIGKILL)
                except (TypeError, psutil.Error):
                    os.kill(pid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGTERM)
        time.sleep(3)
    except OSError:
        keyword = 'cancel' if is_cancel else 'timeout'
        logger.warn("Attempted to %s already finished job, ignoring" % keyword)


def __run__(private_data_dir, hosts, playbook, artifact_dir=None):
    if artifact_dir is None:
        artifact_dir = os.path.join(private_data_dir, "artifacts")

    # Standard out directed to pickup location without event filtering applied
    stdout_filename = os.path.join(artifact_dir, 'stdout')
    os.mknod(stdout_filename, stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR)
    stdout_handle = codecs.open(stdout_filename, 'w', encoding='utf-8')
    stdout_handle = OutputWriter(stdout_handle)

    status, rc = run_isolated_job(
        private_data_dir,
        stdout_handle,
        inventory_hosts=hosts,
        playbook=playbook,
        artifact_dir=artifact_dir
    )
    for filename, data in [
        ('status', status),
        ('rc', rc),
    ]:
        artifact_path = os.path.join(artifact_dir, filename)
        os.mknod(artifact_path, stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR)
        with open(artifact_path, 'w') as f:
            f.write(str(data))


def main():
    version = pkg_resources.require("ansible_runner")[0].version
    parser = argparse.ArgumentParser(description='manage ansible execution')
    parser.add_argument('--version', action='version', version=version)
    parser.add_argument('command', choices=['run', 'start',
                                            'stop', 'is-alive'])
    parser.add_argument('private_data_dir')
    parser.add_argument("--hosts")
    parser.add_argument("-p", "--playbook", default=os.getenv("RUNNER_PLAYBOOK", None))
    parser.add_argument("-i", "--ident",
                        default=uuid4(),
                        help="An identifier that will be used when generating the"
                             "artifacts directory and can be used to uniquely identify a playbook run")
    parser.add_argument("--skip-ident",
                        action="store_true",
                        help="Do not generate a playbook run identifier")
    args = parser.parse_args()

    private_data_dir = args.private_data_dir
    if args.skip_ident:
        artifact_dir = os.path.join(private_data_dir, 'artifacts')
    else:
        print("Ident: {}".format(args.ident))
        artifact_dir = os.path.join(private_data_dir, "artifacts", "{}".format(args.ident))
    if not os.path.exists(artifact_dir):
        os.makedirs(artifact_dir)
    pidfile = os.path.join(private_data_dir, 'pid')
    if args.hosts is None:
        hosts_actual = os.getenv("RUNNER_HOSTS", os.path.join(private_data_dir, "inventory"))
    else:
        hosts_actual = args.hosts

    print("Hosts: {}".format(hosts_actual))
    print("Playbook: {}".format(args.playbook))

    if args.command in ('start', 'run'):
        # create a file to log stderr in case the daemonized process throws
        # an exception before it gets to `pexpect.spawn`
        stderr_path = os.path.join(artifact_dir, 'daemon.log')
        if not os.path.exists(stderr_path):
            os.mknod(stderr_path, stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR)
        stderr = open(stderr_path, 'w+')

        if args.command == 'start':
            import daemon
            from daemon.pidfile import TimeoutPIDLockFile
            context = daemon.DaemonContext(
                pidfile=TimeoutPIDLockFile(pidfile),
                stderr=stderr
            )
        else:
            import threading
            context = threading.Lock()
        with context:
            __run__(private_data_dir, hosts=hosts_actual,
                    playbook=args.playbook, artifact_dir=artifact_dir)
        sys.exit(0)

    try:
        with open(pidfile, 'r') as f:
            pid = int(f.readline())
    except IOError:
        sys.exit(1)

    if args.command == 'stop':
        try:
            with open(os.path.join(private_data_dir, 'args'), 'r') as args:
                handle_termination(pid, json.load(args), 'bwrap')
        except IOError:
            handle_termination(pid, [], 'bwrap')
    elif args.command == 'is-alive':
        try:
            os.kill(pid, signal.SIG_DFL)
            sys.exit(0)
        except OSError:
            sys.exit(1)


if __name__ == '__main__':
    main()
