import os
import re
import stat
import time
import json
import errno
import signal
import shutil
import codecs
import collections

import six
import pexpect
import psutil

import ansible_runner.plugins

from .utils import OutputEventFilter, cleanup_artifact_dir, ensure_str
from .exceptions import CallbackError, AnsibleRunnerException
from ansible_runner.output import debug


class Runner(object):

    def __init__(self, config, cancel_callback=None, remove_partials=True,
                 event_handler=None, finished_callback=None, status_handler=None):
        self.config = config
        self.cancel_callback = cancel_callback
        self.event_handler = event_handler
        self.finished_callback = finished_callback
        self.status_handler = status_handler
        self.canceled = False
        self.timed_out = False
        self.errored = False
        self.status = "unstarted"
        self.rc = None
        self.remove_partials = remove_partials

    def event_callback(self, event_data):
        '''
        Invoked for every Ansible event to collect stdout with the event data and store it for
        later use
        '''
        self.last_stdout_update = time.time()
        job_events_path = os.path.join(self.config.artifact_dir, 'job_events')
        if not os.path.exists(job_events_path):
            os.mkdir(job_events_path, 0o700)
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
                if self.event_handler is not None:
                    should_write = self.event_handler(event_data)
                else:
                    should_write = True
                for plugin in ansible_runner.plugins:
                    ansible_runner.plugins[plugin].event_handler(self.config, event_data)
                if should_write:
                    with codecs.open(full_filename, 'w', encoding='utf-8') as write_file:
                        os.chmod(full_filename, stat.S_IRUSR | stat.S_IWUSR)
                        json.dump(event_data, write_file)
            except IOError as e:
                debug("Failed writing event data: {}".format(e))

    def status_callback(self, status):
        self.status = status
        status_data = dict(status=status, runner_ident=str(self.config.ident))
        for plugin in ansible_runner.plugins:
            ansible_runner.plugins[plugin].status_handler(self.config, status_data)
        if self.status_handler is not None:
            self.status_handler(status_data, runner_config=self.config)

    def run(self):
        '''
        Launch the Ansible task configured in self.config (A RunnerConfig object), returns once the
        invocation is complete
        '''
        self.status_callback('starting')
        stdout_filename = os.path.join(self.config.artifact_dir, 'stdout')
        command_filename = os.path.join(self.config.artifact_dir, 'command')

        try:
            os.makedirs(self.config.artifact_dir, mode=0o700)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(self.config.artifact_dir):
                pass
            else:
                raise
        os.close(os.open(stdout_filename, os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR))

        command = [a.decode('utf-8') if six.PY2 else a for a in self.config.command]
        with codecs.open(command_filename, 'w', encoding='utf-8') as f:
            os.chmod(command_filename, stat.S_IRUSR | stat.S_IWUSR)
            json.dump(
                {'command': command,
                 'cwd': self.config.cwd,
                 'env': self.config.env}, f, ensure_ascii=False
            )

        if self.config.ident is not None:
            cleanup_artifact_dir(os.path.join(self.config.artifact_dir, ".."), self.config.rotate_artifacts)

        stdout_handle = codecs.open(stdout_filename, 'w', encoding='utf-8')
        stdout_handle = OutputEventFilter(stdout_handle, self.event_callback, self.config.suppress_ansible_output, output_json=self.config.json_mode)

        if not isinstance(self.config.expect_passwords, collections.OrderedDict):
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
        env = {
            ensure_str(k): ensure_str(v) if k != 'PATH' and isinstance(v, six.text_type) else v
            for k, v in self.config.env.items()
        }

        self.status_callback('running')
        self.last_stdout_update = time.time()
        try:
            child = pexpect.spawn(
                command[0],
                command[1:],
                cwd=self.config.cwd,
                env=env,
                ignore_sighup=True,
                encoding='utf-8',
                echo=False,
                use_poll=self.config.pexpect_use_poll,
            )
            child.logfile_read = stdout_handle
        except pexpect.exceptions.ExceptionPexpect as e:
            child = collections.namedtuple(
                'MissingProcess', 'exitstatus isalive'
            )(
                exitstatus=127,
                isalive=lambda: False
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
            result_id = child.expect(password_patterns,
                                     timeout=self.config.pexpect_timeout,
                                     searchwindowsize=100)
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
                Runner.handle_termination(child.pid, is_cancel=self.canceled)
            if self.config.idle_timeout and (time.time() - self.last_stdout_update) > self.config.idle_timeout:
                Runner.handle_termination(child.pid, is_cancel=False)
                self.timed_out = True

        stdout_handle.flush()
        stdout_handle.close()

        if self.canceled:
            self.status_callback('canceled')
        elif child.exitstatus == 0 and not self.timed_out:
            self.status_callback('successful')
        elif self.timed_out:
            self.status_callback('timeout')
        else:
            self.status_callback('failed')
        self.rc = child.exitstatus if not (self.timed_out or self.canceled) else 254
        for filename, data in [
            ('status', self.status),
            ('rc', self.rc),
        ]:
            artifact_path = os.path.join(self.config.artifact_dir, filename)
            if not os.path.exists(artifact_path):
                os.close(os.open(artifact_path, os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR))
            with open(artifact_path, 'w') as f:
                f.write(str(data))
        if self.config.directory_isolation_path and self.config.directory_isolation_cleanup:
            shutil.rmtree(self.config.directory_isolation_path)
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
        event_path = os.path.join(self.config.artifact_dir, 'job_events')
        if not os.path.exists(event_path):
            raise AnsibleRunnerException("events missing")
        dir_events = os.listdir(event_path)
        dir_events_actual = []
        for each_file in dir_events:
            if re.match("^[0-9]+-.+json$", each_file):
                dir_events_actual.append(each_file)
        dir_events_actual.sort(key=lambda filenm: int(filenm.split("-", 1)[0]))
        for event_file in dir_events_actual:
            with codecs.open(os.path.join(event_path, event_file), 'r', encoding='utf-8') as event_file_actual:
                event = json.load(event_file_actual)
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
        return dict(skipped=last_event['skipped'],
                    ok=last_event['ok'],
                    dark=last_event['dark'],
                    failures=last_event['failures'],
                    processed=last_event['processed'])

    def host_events(self, host):
        '''
        Given a host name, this will return all task events executed on that host
        '''
        all_host_events = filter(lambda x: 'event_data' in x and 'host' in x['event_data'] and x['event_data']['host'] == host,
                                 self.events)
        return all_host_events

    @classmethod
    def handle_termination(cls, pid, is_cancel=True):
        '''
        Internal method to terminate a subprocess spawned by `pexpect` representing an invocation of runner.

        :param pid:       the process id of the running the job.
        :param is_cancel: flag showing whether this termination is caused by
                          instance's cancel_flag.
        '''
        try:
            main_proc = psutil.Process(pid=pid)
            child_procs = main_proc.children(recursive=True)
            for child_proc in child_procs:
                try:
                    os.kill(child_proc.pid, signal.SIGKILL)
                except (TypeError, OSError):
                    pass
            os.kill(main_proc.pid, signal.SIGKILL)
        except (TypeError, psutil.Error, OSError):
            try:
                os.kill(pid, signal.SIGKILL)
            except (OSError):
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
