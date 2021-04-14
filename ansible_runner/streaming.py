import codecs
import json
import os
import stat
import sys
import tempfile
import uuid
import traceback
try:
    from collections.abc import Mapping
except ImportError:
    from collections import Mapping

import ansible_runner
from ansible_runner.exceptions import ConfigurationError
from ansible_runner.loader import ArtifactLoader
import ansible_runner.plugins
from ansible_runner.utils.streaming import stream_dir, unstream_dir


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


class Worker(object):
    def __init__(self, _input=None, _output=None, **kwargs):
        if _input is None:
            _input = sys.stdin.buffer
        if _output is None:
            _output = sys.stdout.buffer
        self._input = _input
        self._output = _output

        self.kwargs = kwargs
        self.job_kwargs = None

        private_data_dir = kwargs.get('private_data_dir')
        if private_data_dir is None:
            private_data_dir = tempfile.TemporaryDirectory().name
        self.private_data_dir = private_data_dir

        self.status = "unstarted"
        self.rc = None

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

        return self.status, self.rc

    def status_handler(self, status_data, runner_config):
        self.status = status_data['status']
        self._output.write(json.dumps(status_data).encode('utf-8'))
        self._output.write(b'\n')
        self._output.flush()

    def event_handler(self, event_data):
        self._output.write(json.dumps(event_data).encode('utf-8'))
        self._output.write(b'\n')
        self._output.flush()

    def artifacts_handler(self, artifact_dir):
        stream_dir(artifact_dir, self._output)
        self._output.flush()

    def finished_callback(self, runner_obj):
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
            private_data_dir = tempfile.TemporaryDirectory().name
        self.private_data_dir = private_data_dir
        self._loader = ArtifactLoader(self.private_data_dir)

        settings = kwargs.get('settings')
        if settings is None:
            try:
                settings = self._loader.load_file('env/settings', Mapping)
            except ConfigurationError:
                settings = {}
        self.config = MockConfig(settings)

        artifact_dir = kwargs.get('artifact_dir')
        self.artifact_dir = os.path.abspath(
            artifact_dir or os.path.join(self.private_data_dir, 'artifacts'))

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
        full_filename = os.path.join(self.artifact_dir,
                                     'job_events',
                                     '{}-{}.json'.format(event_data['counter'],
                                                         event_data['uuid']))
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
            except (json.decoder.JSONDecodeError, IOError):
                self.status_callback({'status': 'error', 'job_explanation': 'Failed to JSON parse a line from worker stream.'})
                break

            if 'status' in data:
                self.status_callback(data)
            elif 'zipfile' in data:
                self.artifacts_callback(data)
            elif 'eof' in data:
                break
            else:
                self.event_callback(data)

        if self.finished_callback is not None:
            self.finished_callback(self)

        return self.status, self.rc
