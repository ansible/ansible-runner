from __future__ import annotations  # allow newer type syntax until 3.10 is our minimum

import codecs
import json
import os
import stat
import sys
import tempfile
import uuid
import traceback

import ansible_runner
from ansible_runner.exceptions import ConfigurationError
from ansible_runner.loader import ArtifactLoader
import ansible_runner.plugins
from ansible_runner.utils import register_for_cleanup
from ansible_runner.utils.streaming import stream_dir, unstream_dir
from collections.abc import Mapping
from functools import wraps
from threading import Event, RLock, Thread


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return obj.hex
        return json.JSONEncoder.default(self, obj)


class MockConfig(object):
    def __init__(self, settings):
        self.settings = settings


class Transmitter(object):
    def __init__(self, _output=None, **kwargs):
        if _output is None:
            _output = sys.stdout.buffer
        self._output = _output
        self.private_data_dir = os.path.abspath(kwargs.pop('private_data_dir'))
        self.only_transmit_kwargs = kwargs.pop('only_transmit_kwargs', False)
        if 'keepalive_seconds' in kwargs:
            kwargs.pop('keepalive_seconds')  # don't confuse older runners with this Worker-only arg

        self.kwargs = kwargs

        self.status = "unstarted"
        self.rc = None

    def run(self):
        self._output.write(
            json.dumps({'kwargs': self.kwargs}, cls=UUIDEncoder).encode('utf-8')
        )
        self._output.write(b'\n')
        self._output.flush()

        if not self.only_transmit_kwargs:
            stream_dir(self.private_data_dir, self._output)

        self._output.write(json.dumps({'eof': True}).encode('utf-8'))
        self._output.write(b'\n')
        self._output.flush()

        return self.status, self.rc


class Worker:
    def __init__(self, _input=None, _output=None, keepalive_seconds: float | None = None, **kwargs):
        if _input is None:
            _input = sys.stdin.buffer
        if _output is None:
            _output = sys.stdout.buffer

        if keepalive_seconds is None:  # if we didn't get an explicit int value, fall back to envvar
            # FIXME: emit/log a warning and silently continue if this value won't parse
            keepalive_seconds = float(os.environ.get('ANSIBLE_RUNNER_KEEPALIVE_SECONDS', 0))

        self._keepalive_interval_sec = keepalive_seconds
        self._keepalive_thread: Thread | None = None
        self._output_event = Event()
        self._output_lock = RLock()

        self._input = _input
        self._output = _output

        self.kwargs = kwargs
        self.job_kwargs = None

        private_data_dir = kwargs.get('private_data_dir')
        if private_data_dir is None:
            private_data_dir = tempfile.mkdtemp()
            register_for_cleanup(private_data_dir)
        self.private_data_dir = private_data_dir

        self.status = "unstarted"
        self.rc = None

    def _begin_keepalive(self):
        """Starts a keepalive thread at most once"""
        if not self._keepalive_thread:
            self._keepalive_thread = Thread(target=self._keepalive_loop, daemon=True)
            self._keepalive_thread.start()

    def _end_keepalive(self):
        """Disable the keepalive interval and notify the keepalive thread to shut down"""
        self._keepalive_interval_sec = 0
        self._output_event.set()

    def _keepalive_loop(self):
        """Main loop for keepalive injection thread; exits when keepalive interval is <= 0"""
        while self._keepalive_interval_sec > 0:
            # block until output has occurred or keepalive interval elapses
            if self._output_event.wait(timeout=self._keepalive_interval_sec):
                # output was sent before keepalive timeout; reset the event and start waiting again
                self._output_event.clear()
                continue

            # keepalive interval elapsed; try to send a keepalive...
            # pre-acquire the output lock without blocking
            if not self._output_lock.acquire(blocking=False):
                # something else has the lock; output is imminent, so just skip this keepalive
                # NB: a long-running operation under an event handler that's holding this lock but not actually moving
                # output could theoretically block keepalives long enough to cause problems, but it's probably not
                # worth the added locking hassle to be pedantic about it
                continue

            try:
                # were keepalives recently disabled?
                if self._keepalive_interval_sec <= 0:
                    # we're probably shutting down; don't risk corrupting output by writing now, just bail out
                    return
                # output a keepalive event
                # FIXME: this could be a lot smaller (even just `{}`) if a short-circuit discard was guaranteed in
                #  Processor or if other layers were more defensive about missing event keys and/or unknown dictionary
                #  values...
                self.event_handler(dict(event='keepalive', counter=0, uuid=0))
            finally:
                # always release the output lock (
                self._output_lock.release()

    def _synchronize_output_reset_keepalive(wrapped_method):
        """
        Utility decorator to synchronize event writes and flushes to avoid keepalives splatting in the middle of
        mid-write events, and reset keepalive interval on write completion.
        """
        @wraps(wrapped_method)
        def wrapper(self, *args, **kwargs):
            with self._output_lock:
                ret = wrapped_method(self, *args, **kwargs)
                # signal the keepalive thread last, so the timeout restarts after the last write, not before the first
                self._output_event.set()
                return ret

        return wrapper

    def update_paths(self, kwargs):
        if kwargs.get('envvars'):
            if 'ANSIBLE_ROLES_PATH' in kwargs['envvars']:
                roles_path = kwargs['envvars']['ANSIBLE_ROLES_PATH']
                roles_dir = os.path.join(self.private_data_dir, 'roles')
                kwargs['envvars']['ANSIBLE_ROLES_PATH'] = os.path.join(roles_dir, roles_path)
        if kwargs.get('inventory'):
            kwargs['inventory'] = os.path.join(self.private_data_dir, kwargs['inventory'])

        return kwargs

    def run(self):
        self._begin_keepalive()
        try:
            while True:
                try:
                    line = self._input.readline()
                    data = json.loads(line)
                except (json.decoder.JSONDecodeError, IOError):
                    self.status_handler({'status': 'error', 'job_explanation': 'Failed to JSON parse a line from transmit stream.'}, None)
                    self.finished_callback(None)  # send eof line
                    return self.status, self.rc

                if 'kwargs' in data:
                    self.job_kwargs = self.update_paths(data['kwargs'])
                elif 'zipfile' in data:
                    try:
                        unstream_dir(self._input, data['zipfile'], self.private_data_dir)
                    except Exception:
                        self.status_handler({
                            'status': 'error',
                            'job_explanation': 'Failed to extract private data directory on worker.',
                            'result_traceback': traceback.format_exc()
                        }, None)
                        self.finished_callback(None)  # send eof line
                        return self.status, self.rc
                elif 'eof' in data:
                    break

            self.kwargs.update(self.job_kwargs)
            self.kwargs['quiet'] = True
            self.kwargs['suppress_ansible_output'] = True
            self.kwargs['private_data_dir'] = self.private_data_dir
            self.kwargs['status_handler'] = self.status_handler
            self.kwargs['event_handler'] = self.event_handler
            self.kwargs['artifacts_handler'] = self.artifacts_handler
            self.kwargs['finished_callback'] = self.finished_callback

            r = ansible_runner.interface.run(**self.kwargs)
            self.status, self.rc = r.status, r.rc

            # FIXME: do cleanup on the tempdir
        finally:
            self._end_keepalive()

        return self.status, self.rc

    @_synchronize_output_reset_keepalive
    def status_handler(self, status_data, runner_config):
        self.status = status_data['status']
        self._output.write(json.dumps(status_data).encode('utf-8'))
        self._output.write(b'\n')
        self._output.flush()

    @_synchronize_output_reset_keepalive
    def event_handler(self, event_data):
        self._output.write(json.dumps(event_data).encode('utf-8'))
        self._output.write(b'\n')
        self._output.flush()

    @_synchronize_output_reset_keepalive
    def artifacts_handler(self, artifact_dir):
        stream_dir(artifact_dir, self._output)
        self._output.flush()

    @_synchronize_output_reset_keepalive
    def finished_callback(self, runner_obj):
        self._end_keepalive()  # ensure that we can't splat a keepalive event after the eof event
        self._output.write(json.dumps({'eof': True}).encode('utf-8'))
        self._output.write(b'\n')
        self._output.flush()


class Processor(object):
    def __init__(self, _input=None, status_handler=None, event_handler=None,
                 artifacts_handler=None, cancel_callback=None, finished_callback=None, **kwargs):
        if _input is None:
            _input = sys.stdin.buffer
        self._input = _input

        self.quiet = kwargs.get('quiet')

        private_data_dir = kwargs.get('private_data_dir')
        if private_data_dir is None:
            private_data_dir = tempfile.mkdtemp()
        self.private_data_dir = private_data_dir
        self._loader = ArtifactLoader(self.private_data_dir)

        settings = kwargs.get('settings')
        if settings is None:
            try:
                settings = self._loader.load_file('env/settings', Mapping)
            except ConfigurationError:
                settings = {}
        self.config = MockConfig(settings)

        if kwargs.get('artifact_dir'):
            self.artifact_dir = os.path.abspath(kwargs.get('artifact_dir'))
        else:
            project_artifacts = os.path.abspath(os.path.join(self.private_data_dir, 'artifacts'))
            if kwargs.get('ident'):
                self.artifact_dir = os.path.join(project_artifacts, "{}".format(kwargs.get('ident')))
            else:
                self.artifact_dir = project_artifacts

        self.status_handler = status_handler
        self.event_handler = event_handler
        self.artifacts_handler = artifacts_handler

        self.cancel_callback = cancel_callback  # FIXME: unused
        self.finished_callback = finished_callback

        self.status = "unstarted"
        self.rc = None

    def status_callback(self, status_data):
        self.status = status_data['status']
        if self.status == 'starting':
            self.config.command = status_data.get('command')
            self.config.env = status_data.get('env')
            self.config.cwd = status_data.get('cwd')

        for plugin in ansible_runner.plugins:
            ansible_runner.plugins[plugin].status_handler(self.config, status_data)
        if self.status_handler is not None:
            self.status_handler(status_data, runner_config=self.config)

    def event_callback(self, event_data):
        # FIXME: this needs to be more defensive to not blow up on "malformed" events or new values it doesn't recognize
        counter = event_data.get('counter')
        uuid = event_data.get('uuid')

        if not counter or not uuid:
            # FIXME: log a warning about a malformed event?
            return

        full_filename = os.path.join(self.artifact_dir,
                                     'job_events',
                                     f'{counter}-{uuid}.json')

        if not self.quiet and 'stdout' in event_data:
            print(event_data['stdout'])

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

    def artifacts_callback(self, artifacts_data):
        length = artifacts_data['zipfile']
        unstream_dir(self._input, length, self.artifact_dir)

        if self.artifacts_handler is not None:
            self.artifacts_handler(self.artifact_dir)

    def run(self):
        job_events_path = os.path.join(self.artifact_dir, 'job_events')
        if not os.path.exists(job_events_path):
            os.makedirs(job_events_path, 0o700, exist_ok=True)

        while True:
            try:
                line = self._input.readline()
                data = json.loads(line)
            except (json.decoder.JSONDecodeError, IOError) as exc:
                self.status_callback({
                    'status': 'error',
                    'job_explanation': (
                        f'Failed to JSON parse a line from worker stream. Error: {exc} Line with invalid JSON data: {line[:1000]}'
                    )
                })
                break

            if 'status' in data:
                self.status_callback(data)
            elif 'zipfile' in data:
                self.artifacts_callback(data)
            elif 'eof' in data:
                break
            elif data.get('event') == 'keepalive':
                # just ignore keepalives
                continue
            else:
                self.event_callback(data)

        if self.finished_callback is not None:
            self.finished_callback(self)

        return self.status, self.rc
