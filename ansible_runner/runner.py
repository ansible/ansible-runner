import os
import stat
import time
import json
import errno
import signal
from subprocess import Popen, PIPE, CalledProcessError, TimeoutExpired, run as run_subprocess
import shutil
import codecs
import collections
import datetime
import logging

import six
import pexpect

import ansible_runner.plugins

from .utils import OutputEventFilter, cleanup_artifact_dir, ensure_str, collect_new_events
from .exceptions import CallbackError, AnsibleRunnerException
from ansible_runner.output import debug

logger = logging.getLogger('ansible-runner')


class Runner(object):

    def __init__(self, config, cancel_callback=None, remove_partials=True, event_handler=None,
                 artifacts_handler=None, finished_callback=None, status_handler=None):
        self.config = config
        self.cancel_callback = cancel_callback
        self.event_handler = event_handler
        self.artifacts_handler = artifacts_handler
        self.finished_callback = finished_callback
        self.status_handler = status_handler
        self.canceled = False
        self.timed_out = False
        self.errored = False
        self.status = "unstarted"
        self.rc = None
        self.remove_partials = remove_partials

        # default runner mode to pexpect
        self.runner_mode = self.config.runner_mode if hasattr(self.config, 'runner_mode') else 'pexpect'

        self.resource_profiling = self.config.resource_profiling if hasattr(self.config, 'resource_profiling') else False
        self.directory_isolation_path = self.config.directory_isolation_path if hasattr(self.config, 'directory_isolation_path') else None
        self.directory_isolation_cleanup = self.config.directory_isolation_cleanup if hasattr(self.config, 'directory_isolation_cleanup') else None
        self.process_isolation = self.config.process_isolation if hasattr(self.config, 'process_isolation') else None
        self.process_isolation_path_actual = self.config.process_isolation_path_actual if hasattr(self.config, 'process_isolation_path_actual') else None

    def event_callback(self, event_data):
        '''
        Invoked for every Ansible event to collect stdout with the event data and store it for
        later use
        '''
        self.last_stdout_update = time.time()
        if 'uuid' in event_data:
            filename = '{}-partial.json'.format(event_data['uuid'])
            partial_filename = os.path.join(self.config.artifact_dir,
                                            'job_events',
                                            filename)
            full_filename = os.path.join(self.config.artifact_dir,
                                         'job_events',
                                         '{}-{}.json'.format(event_data['counter'],
                                                             event_data['uuid']))
            try:
                event_data.update(dict(runner_ident=str(self.config.ident)))
                try:
                    with codecs.open(partial_filename, 'r', encoding='utf-8') as read_file:
                        partial_event_data = json.load(read_file)
                    event_data.update(partial_event_data)
                    if self.remove_partials:
                        os.remove(partial_filename)
                except IOError:
                    debug("Failed to open ansible stdout callback plugin partial data file {}".format(partial_filename))

                # prefer 'created' from partial data, but verbose events set time here
                if 'created' not in event_data:
                    event_data['created'] = datetime.datetime.utcnow().isoformat()

                if self.event_handler is not None:
                    should_write = self.event_handler(event_data)
                else:
                    should_write = True
                for plugin in ansible_runner.plugins:
                    ansible_runner.plugins[plugin].event_handler(self.config, event_data)
                if should_write:
                    temporary_filename = full_filename + '.tmp'
                    with codecs.open(temporary_filename, 'w', encoding='utf-8') as write_file:
                        os.chmod(temporary_filename, stat.S_IRUSR | stat.S_IWUSR)
                        json.dump(event_data, write_file)
                    os.rename(temporary_filename, full_filename)
            except IOError as e:
                debug("Failed writing event data: {}".format(e))

    def status_callback(self, status):
        self.status = status
        status_data = {'status': status, 'runner_ident': str(self.config.ident)}
        if status == 'starting':
            status_data.update({'command': self.config.command, 'env': self.config.env, 'cwd': self.config.cwd})
        for plugin in ansible_runner.plugins:
            ansible_runner.plugins[plugin].status_handler(self.config, status_data)
        if self.status_handler is not None:
            self.status_handler(status_data, runner_config=self.config)

    def run(self):
        '''
        Launch the Ansible task configured in self.config (A RunnerConfig object), returns once the
        invocation is complete
        '''
        password_patterns = []
        password_values = []

        self.status_callback('starting')
        stdout_filename = os.path.join(self.config.artifact_dir, 'stdout')
        command_filename = os.path.join(self.config.artifact_dir, 'command')
        stderr_filename = os.path.join(self.config.artifact_dir, 'stderr')

        try:
            os.makedirs(self.config.artifact_dir, mode=0o700)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(self.config.artifact_dir):
                pass
            else:
                raise
        os.close(os.open(stdout_filename, os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR))

        job_events_path = os.path.join(self.config.artifact_dir, 'job_events')
        if not os.path.exists(job_events_path):
            os.mkdir(job_events_path, 0o700)

        command = self.config.command
        with codecs.open(command_filename, 'w', encoding='utf-8') as f:
            os.chmod(command_filename, stat.S_IRUSR | stat.S_IWUSR)
            json.dump(
                {'command': command,
                 'cwd': self.config.cwd,
                 'env': self.config.env}, f, ensure_ascii=False
            )

        if self.config.ident is not None:
            cleanup_artifact_dir(os.path.join(self.config.artifact_dir, ".."), self.config.rotate_artifacts)

        if hasattr(self.config, 'suppress_ansible_output'):
            suppress_ansible_output = self.config.suppress_ansible_output
        else:
            suppress_ansible_output = False

        stdout_handle = codecs.open(stdout_filename, 'w', encoding='utf-8')
        stdout_handle = OutputEventFilter(stdout_handle, self.event_callback, suppress_ansible_output, output_json=self.config.json_mode)
        stderr_handle = codecs.open(stderr_filename, 'w', encoding='utf-8')
        stderr_handle = OutputEventFilter(stderr_handle, self.event_callback, suppress_ansible_output, output_json=self.config.json_mode)

        if self.runner_mode == 'pexpect' and not isinstance(self.config.expect_passwords, collections.OrderedDict):
            # We iterate over `expect_passwords.keys()` and
            # `expect_passwords.values()` separately to map matched inputs to
            # patterns and choose the proper string to send to the subprocess;
            # enforce usage of an OrderedDict so that the ordering of elements in
            # `keys()` matches `values()`.
            expect_passwords = collections.OrderedDict(self.config.expect_passwords)
            password_patterns = list(expect_passwords.keys())
            password_values = list(expect_passwords.values())

        # pexpect needs all env vars to be utf-8 encoded bytes
        # https://github.com/pexpect/pexpect/issues/512

        # Use a copy so as not to cause problems when serializing the job_env.
        if self.config.containerized:
            # We call the actual docker or podman executable right where we are
            cwd = os.getcwd()
            # If this is containerized, the shell environment calling podman has little
            # to do with the actual job environment, but still needs PATH, auth, etc.
            pexpect_env = os.environ.copy()
            # But we still rely on env vars to pass secrets
            pexpect_env.update(self.config.env)
            # Write the keys to pass into container to expected file in artifacts dir
            # option expecting should have already been written in ansible_runner.runner_config
            env_file_host = os.path.join(self.config.artifact_dir, 'env.list')
            with open(env_file_host, 'w') as f:
                f.write('\n'.join(list(self.config.env.keys())))
        else:
            cwd = self.config.cwd
            pexpect_env = self.config.env
        env = {
            ensure_str(k): ensure_str(v) if k != 'PATH' and isinstance(v, six.text_type) else v
            for k, v in pexpect_env.items()
        }

        # Prepare to collect performance data
        if self.resource_profiling:
            cgroup_path = '{0}/{1}'.format(self.config.resource_profiling_base_cgroup, self.config.ident)

            import getpass
            import grp
            user = getpass.getuser()
            group = grp.getgrgid(os.getgid()).gr_name

            cmd = 'cgcreate -a {user}:{group} -t {user}:{group} -g cpuacct,memory,pids:{}'.format(cgroup_path, user=user, group=group)
            proc = Popen(cmd, stdout=PIPE, stderr=PIPE, shell=True)
            _, stderr = proc.communicate()
            if proc.returncode:
                # Unable to create cgroup
                logger.error('Unable to create cgroup: {}'.format(stderr))
                raise RuntimeError('Unable to create cgroup: {}'.format(stderr))
            else:
                logger.info("Created cgroup '{}'".format(cgroup_path))


        self.status_callback('running')
        self.last_stdout_update = time.time()

        # The subprocess runner interface provides stdin/stdout/stderr with streaming capability
        # to the caller if input_fd/output_fd/error_fd is passed to config class.
        # Alsp, provides an workaround for known issue in pexpect for long running non-interactive process
        # https://pexpect.readthedocs.io/en/stable/commonissues.html#truncated-output-just-before-child-exits
        if self.runner_mode == 'subprocess':
            if hasattr(self.config, 'input_fd') and self.config.input_fd:
                input_fd = self.config.input_fd
            else:
                input_fd = None

            if hasattr(self.config, 'output_fd') and self.config.output_fd:
                output_fd = self.config.output_fd
            else:
                output_fd = PIPE

            if hasattr(self.config, 'error_fd') and self.config.error_fd:
                error_fd = self.config.error_fd
            else:
                error_fd = PIPE

            subprocess_timeout = self.config.subprocess_timeout if hasattr(self.config, 'subprocess_timeout') else None
            try:
                stdout_response = ''
                stderr_response = ''
                kwargs = {
                    'cwd': cwd,
                    'env': env,
                    'stdin': input_fd,
                    'stdout': output_fd,
                    'stderr': error_fd,
                    'check': True,
                    'universal_newlines': True,
                    'shell': True
                }
                if subprocess_timeout is not None:
                    kwargs.update({'timeout': subprocess_timeout})

                proc_out = run_subprocess( " ".join(command), **kwargs)

                stdout_response = proc_out.stdout
                stderr_response = proc_out.stderr
                self.rc = proc_out.returncode
            except CalledProcessError as exc:
                logger.debug("{cmd} execution failed, returncode: {rc}, output: {output}, stdout: {stdout}, stderr: {stderr}".format(
                    cmd=exc.cmd, rc=exc.returncode, output=exc.output, stdout=exc.stdout, stderr=exc.stderr))
                self.rc = exc.returncode
                self.errored = True
                stdout_response = exc.stdout
                stderr_response = exc.stderr
            except TimeoutExpired as exc:
                logger.debug("{cmd} execution timedout, timeout: {timeout}, output: {output}, stdout: {stdout}, stderr: {stderr}".format(
                    cmd=exc.cmd, timeout=exc.timeout, output=exc.output, stdout=exc.stdout, stderr=exc.stderr))
                self.rc = 254
                stdout_response = exc.stdout
                stderr_response = exc.stderr
                self.timed_out = True
            except Exception as exc:
                import traceback
                stderr_response = traceback.format_exc()
                self.rc = 254
                self.errored = True
                logger.debug("received execption: {exc}".format(exc=str(exc)))

            if self.timed_out or self.errored:
                self.kill_container()

            if stdout_response is not None:
                if isinstance(stdout_response, bytes):
                    stdout_response = stdout_response.decode()
                stdout_handle.write(stdout_response)
            if stderr_response is not None:
                if isinstance(stderr_response, bytes):
                    stderr_response = stderr_response.decode()
                stderr_handle.write(stderr_response)
        else:
            try:
                child = pexpect.spawn(
                    command[0],
                    command[1:],
                    cwd=cwd,
                    env=env,
                    ignore_sighup=True,
                    encoding='utf-8',
                    codec_errors='replace',
                    echo=False,
                    use_poll=self.config.pexpect_use_poll,
                )
                child.logfile_read = stdout_handle
            except pexpect.exceptions.ExceptionPexpect as e:
                child = collections.namedtuple(
                    'MissingProcess', 'exitstatus isalive close'
                )(
                    exitstatus=127,
                    isalive=lambda: False,
                    close=lambda: None,
                )

                def _decode(x):
                    return x.decode('utf-8') if six.PY2 else x

                # create the events directory (the callback plugin won't run, so it
                # won't get created)
                events_directory = os.path.join(self.config.artifact_dir, 'job_events')
                if not os.path.exists(events_directory):
                    os.mkdir(events_directory, 0o700)
                stdout_handle.write(_decode(str(e)))
                stdout_handle.write(_decode('\n'))

            job_start = time.time()
            while child.isalive():
                result_id = child.expect(password_patterns, timeout=self.config.pexpect_timeout, searchwindowsize=100)
                password = password_values[result_id]
                if password is not None:
                    child.sendline(password)
                    self.last_stdout_update = time.time()
                if self.cancel_callback:
                    try:
                        self.canceled = self.cancel_callback()
                    except Exception as e:
                        # TODO: logger.exception('Could not check cancel callback - cancelling immediately')
                        #if isinstance(extra_update_fields, dict):
                        #    extra_update_fields['job_explanation'] = "System error during job execution, check system logs"
                        raise CallbackError("Exception in Cancel Callback: {}".format(e))
                if self.config.job_timeout and not self.canceled and (time.time() - job_start) > self.config.job_timeout:
                    self.timed_out = True
                    # if isinstance(extra_update_fields, dict):
                    #     extra_update_fields['job_explanation'] = "Job terminated due to timeout"
                if self.canceled or self.timed_out or self.errored:
                    self.kill_container()
                    Runner.handle_termination(child.pid, is_cancel=self.canceled)
                if self.config.idle_timeout and (time.time() - self.last_stdout_update) > self.config.idle_timeout:
                    self.kill_container()
                    Runner.handle_termination(child.pid, is_cancel=False)
                    self.timed_out = True

            stdout_handle.flush()
            stdout_handle.close()
            child.close()
            self.rc = child.exitstatus if not (self.timed_out or self.canceled) else 254

        if self.canceled:
            self.status_callback('canceled')
        elif self.rc == 0 and not self.timed_out:
            self.status_callback('successful')
        elif self.timed_out:
            self.status_callback('timeout')
        else:
            self.status_callback('failed')

        for filename, data in [
            ('status', self.status),
            ('rc', self.rc),
        ]:
            artifact_path = os.path.join(self.config.artifact_dir, filename)
            if not os.path.exists(artifact_path):
                os.close(os.open(artifact_path, os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR))
            with open(artifact_path, 'w') as f:
                f.write(str(data))
        if self.directory_isolation_path and self.directory_isolation_cleanup:
            shutil.rmtree(self.directory_isolation_path)
        if self.process_isolation and self.process_isolation_path_actual:
            def _delete(retries=15):
                try:
                    shutil.rmtree(self.process_isolation_path_actual)
                except OSError as e:
                    res = False
                    if e.errno == 16 and retries > 0:
                        time.sleep(1)
                        res = _delete(retries=retries - 1)
                    if not res:
                        raise
                return True
            _delete()
        if self.resource_profiling:
            cmd = 'cgdelete -g cpuacct,memory,pids:{}'.format(cgroup_path)
            proc = Popen(cmd, stdout=PIPE, stderr=PIPE, shell=True)
            _, stderr = proc.communicate()
            if proc.returncode:
                logger.error('Failed to delete cgroup: {}'.format(stderr))
                raise RuntimeError('Failed to delete cgroup: {}'.format(stderr))

        if self.artifacts_handler is not None:
            try:
                self.artifacts_handler(self.config.artifact_dir)
            except Exception as e:
                raise CallbackError("Exception in Artifact Callback: {}".format(e))

        if self.finished_callback is not None:
            try:
                self.finished_callback(self)
            except Exception as e:
                raise CallbackError("Exception in Finished Callback: {}".format(e))
        return self.status, self.rc

    @property
    def stdout(self):
        '''
        Returns an open file handle to the stdout representing the Ansible run
        '''
        stdout_path = os.path.join(self.config.artifact_dir, 'stdout')
        if not os.path.exists(stdout_path):
            raise AnsibleRunnerException("stdout missing")
        return open(os.path.join(self.config.artifact_dir, 'stdout'), 'r')

    @property
    def stderr(self):
        '''
        Returns an open file handle to the stderr representing the Ansible run
        '''
        stderr_path = os.path.join(self.config.artifact_dir, 'stderr')
        if not os.path.exists(stderr_path):
            raise AnsibleRunnerException("stderr missing")
        return open(os.path.join(self.config.artifact_dir, 'stderr'), 'r')

    @property
    def events(self):
        '''
        A generator that will return all ansible job events in the order that they were emitted from Ansible

        Example:

            {
               "event":"runner_on_ok",
               "uuid":"00a50d9c-161a-4b74-b978-9f60becaf209",
               "stdout":"ok: [localhost] => {\\r\\n    \\"   msg\\":\\"Test!\\"\\r\\n}",
               "counter":6,
               "pid":740,
               "created":"2018-04-05T18:24:36.096725",
               "end_line":10,
               "start_line":7,
               "event_data":{
                  "play_pattern":"all",
                  "play":"all",
                  "task":"debug",
                  "task_args":"msg=Test!",
                  "remote_addr":"localhost",
                  "res":{
                     "msg":"Test!",
                     "changed":false,
                     "_ansible_verbose_always":true,
                     "_ansible_no_log":false
                  },
                  "pid":740,
                  "play_uuid":"0242ac11-0002-443b-cdb1-000000000006",
                  "task_uuid":"0242ac11-0002-443b-cdb1-000000000008",
                  "event_loop":null,
                  "playbook_uuid":"634edeee-3228-4c17-a1b4-f010fdd42eb2",
                  "playbook":"test.yml",
                  "task_action":"debug",
                  "host":"localhost",
                  "task_path":"/tmp/demo/project/test.yml:3"
               }
           }
        '''
        # collection of all the events that were yielded
        old_events = {}
        event_path = os.path.join(self.config.artifact_dir, 'job_events')

        # Wait for events dir to be created
        now = datetime.datetime.now()
        while not os.path.exists(event_path):
            time.sleep(0.05)
            wait_time = datetime.datetime.now() - now
            if wait_time.total_seconds() > 60:
                raise AnsibleRunnerException("events directory is missing: %s" % event_path)

        while self.status == "running":
            for event, old_evnts in collect_new_events(event_path, old_events):
                old_events = old_evnts
                yield event

        # collect new events that were written after the playbook has finished
        for event, old_evnts in collect_new_events(event_path, old_events):
            old_events = old_evnts
            yield event

    @property
    def stats(self):
        '''
        Returns the final high level stats from the Ansible run

        Example:
            {'dark': {}, 'failures': {}, 'skipped': {}, 'ok': {u'localhost': 2}, 'processed': {u'localhost': 1}}
        '''
        last_event = list(filter(lambda x: 'event' in x and x['event'] == 'playbook_on_stats',
                                 self.events))
        if not last_event:
            return None
        last_event = last_event[0]['event_data']
        return dict(skipped=last_event.get('skipped',{}),
                    ok=last_event.get('ok',{}),
                    dark=last_event.get('dark',{}),
                    failures=last_event.get('failures',{}),
                    ignored=last_event.get('ignored', {}),
                    rescued=last_event.get('rescued', {}),
                    processed=last_event.get('processed',{}),
                    changed=last_event.get('changed',{}))


    def host_events(self, host):
        '''
        Given a host name, this will return all task events executed on that host
        '''
        all_host_events = filter(lambda x: 'event_data' in x and 'host' in x['event_data'] and x['event_data']['host'] == host,
                                 self.events)
        return all_host_events

    def kill_container(self):
        '''
        Internal method to terminate a container being used for job isolation
        '''
        container_name = self.config.container_name
        if container_name:
            container_cli = self.config.process_isolation_executable
            cmd = '{} kill {}'.format(container_cli, container_name)
            proc = Popen(cmd, stdout=PIPE, stderr=PIPE, shell=True)
            _, stderr = proc.communicate()
            if proc.returncode:
                logger.info('Error from {} kill {} command:\n{}'.format(container_cli, container_name, stderr))
            else:
                logger.info("Killed container {}".format(container_name))

    @classmethod
    def handle_termination(cls, pid, pidfile=None, is_cancel=True):
        '''
        Internal method to terminate a subprocess spawned by `pexpect` representing an invocation of runner.

        :param pid:       the process id of the running the job.
        :param pidfile:   the daemon's PID file
        :param is_cancel: flag showing whether this termination is caused by
                          instance's cancel_flag.
        '''

        try:
            pgroup = os.getpgid(pid)
            os.killpg(pgroup, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
        try:
            os.remove(pidfile)
        except (TypeError, OSError):
            pass


    def get_fact_cache(self, host):
        '''
        Get the entire fact cache only if the fact_cache_type is 'jsonfile'
        '''
        if self.config.fact_cache_type != 'jsonfile':
            raise Exception('Unsupported fact cache type.  Only "jsonfile" is supported for reading and writing facts from ansible-runner')
        fact_cache = os.path.join(self.config.fact_cache, host)
        if os.path.exists(fact_cache):
            with open(fact_cache) as f:
                return json.loads(f.read())
        return {}

    def set_fact_cache(self, host, data):
        '''
        Set the entire fact cache data only if the fact_cache_type is 'jsonfile'
        '''
        if self.config.fact_cache_type != 'jsonfile':
            raise Exception('Unsupported fact cache type.  Only "jsonfile" is supported for reading and writing facts from ansible-runner')
        fact_cache = os.path.join(self.config.fact_cache, host)
        if not os.path.exists(os.path.dirname(fact_cache)):
            os.makedirs(os.path.dirname(fact_cache), mode=0o700)
        with open(fact_cache, 'w') as f:
            return f.write(json.dumps(data))
