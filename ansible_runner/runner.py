import os
import stat
import time
import errno
import signal
import codecs
import collections

import pexpect
import psutil

from .utils import OutputWriter
from .exceptions import CallbackError, AnsibleRunnerException


class Runner(object):

    def __init__(self, config, cancel_callback=None):
        self.config = config
        self.cancel_callback = cancel_callback
        self.canceled = False
        self.timed_out = False
        self.errored = False
        self.status = "unstarted"
        self.rc = None


    def run(self):
        self.status = "starting"
        stdout_filename = os.path.join(self.config.artifact_dir, 'stdout')

        try:
            os.makedirs(self.config.artifact_dir)
            os.mknod(stdout_filename, stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(self.config.artifact_dir):
                pass
            else:
                raise

        stdout_handle = codecs.open(stdout_filename, 'w', encoding='utf-8')
        stdout_handle = OutputWriter(stdout_handle)

        if not isinstance(self.config.expect_passwords, collections.OrderedDict):
            # We iterate over `expect_passwords.keys()` and
            # `expect_passwords.values()` separately to map matched inputs to
            # patterns and choose the proper string to send to the subprocess;
            # enforce usage of an OrderedDict so that the ordering of elements in
            # `keys()` matches `values()`.
            expect_passwords = collections.OrderedDict(self.config.expect_passwords)
        password_patterns = expect_passwords.keys()
        password_values = expect_passwords.values()

        self.status = 'running'
        child = pexpect.spawn(
            self.config.command[0],
            self.config.command[1:],
            cwd=self.config.cwd,
            env=self.config.env,
            ignore_sighup=True,
            encoding='utf-8',
            echo=False,
        )
        child.logfile_read = stdout_handle
        last_stdout_update = time.time()

        job_start = time.time()
        while child.isalive():
            result_id = child.expect(password_patterns,
                                     timeout=self.config.pexpect_timeout,
                                     searchwindowsize=100)
            password = password_values[result_id]
            if password is not None:
                child.sendline(password)
                last_stdout_update = time.time()
            if self.cancel_callback:
                try:
                    self.canceled = self.cancel_callback()
                except Exception:
                    # TODO: logger.exception('Could not check cancel callback - cancelling immediately')
                    #if isinstance(extra_update_fields, dict):
                    #    extra_update_fields['job_explanation'] = "System error during job execution, check system logs"
                    raise CallbackError("Exception in Cancel Callback")
            if not self.canceled and self.config.job_timeout != 0 and (time.time() - job_start) > self.config.job_timeout:
                self.timed_out = True
                # if isinstance(extra_update_fields, dict):
                #     extra_update_fields['job_explanation'] = "Job terminated due to timeout"
            if self.canceled or self.timed_out or self.errored:
                # TODO: proot_cmd
                Runner.handle_termination(child.pid, child.args, proot_cmd=None, is_cancel=self.canceled)
            if self.config.idle_timeout and (time.time() - last_stdout_update) > self.config.idle_timeout:
                child.close(True)
                self.canceled = True

        if self.canceled:
            self.status = "canceled"
        elif child.exitstatus == 0 and not self.timed_out:
            self.status = "successful"
        else:
            self.status = "failed"
        self.rc = child.exitstatus

        for filename, data in [
            ('status', self.status),
            ('rc', self.rc),
        ]:
            artifact_path = os.path.join(self.config.artifact_dir, filename)
            if not os.path.exists(artifact_path):
                os.mknod(artifact_path, stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR)
            with open(artifact_path, 'w') as f:
                f.write(str(data))
        return self.status, self.rc

    @property
    def stdout(self):
        stdout_path = os.path.join(self.config.artifact_dir, 'stdout')
        if not os.path.exists(stdout_path):
            raise AnsibleRunnerException("stdout missing")
        return open(os.path.join(self.config.artifact_dir, 'stdout'), 'r')

    def events(self):
        pass

    @classmethod
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
            raise
            #keyword = 'cancel' if is_cancel else 'timeout'
            #TODO: logger.warn("Attempted to %s already finished job, ignoring" % keyword)
