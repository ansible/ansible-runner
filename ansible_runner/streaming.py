import codecs
import io
import json
import os
import stat
import sys
import tempfile
import uuid
import zipfile

import ansible_runner
import ansible_runner.plugins
from ansible_runner import utils


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return obj.hex
        return json.JSONEncoder.default(self, obj)




class Transmitter(object):
    def __init__(self, _output=None, **kwargs):
        if _output is None:
            _output = sys.stdout.buffer
        self._output = _output
        self.kwargs = kwargs

        self.status = "unstarted"
        self.rc = None

    def run(self):
        self._output.write(
            json.dumps({'kwargs': self.kwargs}, cls=UUIDEncoder).encode('utf-8')
        )
        self._output.flush()

        private_data_dir = self.kwargs.get('private_data_dir')
        self._output.write(utils.stream_dir(private_data_dir))
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

    def run(self):
        while True:
            line = self._input.readline()
            data = json.loads(line)

            if 'kwargs' in data:
                self.job_kwargs = data['kwargs']
            elif 'zipfile' in data:
                zip_data = self._input.read(data['zipfile'])
                buf = io.BytesIO(zip_data)
                with zipfile.ZipFile(buf, 'r') as archive:
                    archive.extractall(path=self.private_data_dir)
            elif 'eof' in data:
                break

        self.kwargs.update(self.job_kwargs)
        self.kwargs['quiet'] = True
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
        self._output.write(utils.stream_dir(artifact_dir))
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

        self.kwargs = kwargs
        self.config = ansible_runner.RunnerConfig(**kwargs)
        self.status_handler = status_handler
        self.event_handler = event_handler
        self.artifacts_handler = artifacts_handler

        self.cancel_callback = cancel_callback
        self.finished_callback = finished_callback

        self.status = "unstarted"
        self.rc = None

    def status_callback(self, status_data):
        self.status = status_data['status']

        for plugin in ansible_runner.plugins:
            ansible_runner.plugins[plugin].status_handler(self.config, status_data)
        if self.status_handler is not None:
            self.status_handler(status_data, runner_config=self.config)

    def event_callback(self, event_data):
        full_filename = os.path.join(self.config.artifact_dir,
                                     'job_events',
                                     '{}-{}.json'.format(event_data['counter'],
                                                         event_data['uuid']))

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
        buf = io.BytesIO(artifacts_data)
        with zipfile.ZipFile(buf, 'r') as archive:
            archive.extractall(path=self.config.artifact_dir)

        if self.artifacts_handler is not None:
            self.artifacts_handler(self.config.artifact_dir)

    def run(self):
        self.config.prepare()

        job_events_path = os.path.join(self.config.artifact_dir, 'job_events')
        if not os.path.exists(job_events_path):
            os.mkdir(job_events_path, 0o700)

        while True:
            line = self._input.readline()
            data = json.loads(line)

            if 'status' in data:
                self.status_callback(data)
            elif 'zipfile' in data:
                self.artifacts_callback(self._input.read(data['zipfile']))
            elif 'eof' in data:
                break
            else:
                self.event_callback(data)

        if self.finished_callback is not None:
            self.finished_callback(self)

        return self.status, self.rc
