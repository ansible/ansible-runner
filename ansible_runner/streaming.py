import base64
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


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return obj.hex
        return json.JSONEncoder.default(self, obj)


# List of kwargs options to the run method that should be sent to the remote executor.
remote_run_options = (
    'forks',
    'host_pattern',
    'ident',
    'ignore_logging',
    'inventory',
    'limit',
    'module',
    'module_args',
    'omit_event_data',
    'only_failed_event_data',
    'playbook',
    'verbosity',
)


class Transmitter(object):
    def __init__(self, _output=None, **kwargs):
        if _output is None:
            _output = sys.stdout.buffer
        self._output = _output
        self.kwargs = kwargs
        self.config = ansible_runner.RunnerConfig(**kwargs)

        self.status = "unstarted"
        self.rc = None

    def run(self):
        self.config.prepare()
        remote_options = {key: value for key, value in self.kwargs.items() if key in remote_run_options}

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            private_data_dir = self.kwargs.get('private_data_dir', None)
            if private_data_dir:
                for dirpath, dirs, files in os.walk(private_data_dir):
                    relpath = os.path.relpath(dirpath, private_data_dir)
                    if relpath == ".":
                        relpath = ""
                    for fname in files:
                        archive.write(os.path.join(dirpath, fname), arcname=os.path.join(relpath, fname))

            kwargs = json.dumps(remote_options, cls=UUIDEncoder)
            archive.writestr('kwargs', kwargs)
            archive.close()
        buf.flush()

        data = {
            'private_data_dir': True,
            'payload': base64.b64encode(buf.getvalue()).decode('ascii'),
        }
        self._output.flush()
        self._output.write(json.dumps(data).encode('utf-8'))
        self._output.write(b'\n')
        self._output.flush()
        self._output.close()


class Worker(object):
    def __init__(self, _input=None, _output=None, **kwargs):
        if _input is None:
            _input = sys.stdin.buffer
        if _output is None:
            _output = sys.stdout.buffer
        self._input = _input
        self._output = _output

        self.kwargs = kwargs

        self.private_data_dir = tempfile.TemporaryDirectory().name

    def run(self):
        for line in self._input:
            data = json.loads(line)
            if data.get('private_data_dir'):
                buf = io.BytesIO(base64.b64decode(data['payload']))
                with zipfile.ZipFile(buf, 'r') as archive:
                    archive.extractall(path=self.private_data_dir)

        kwargs_path = os.path.join(self.private_data_dir, 'kwargs')
        if os.path.exists(kwargs_path):
            with open(kwargs_path, "r") as kwf:
                kwargs = json.load(kwf)
            if not isinstance(kwargs, dict):
                raise ValueError("Invalid kwargs data")
        else:
            kwargs = {}

        self.kwargs.update(kwargs)

        self.kwargs['quiet'] = True
        self.kwargs['private_data_dir'] = self.private_data_dir
        self.kwargs['status_handler'] = self.status_handler
        self.kwargs['event_handler'] = self.event_handler
        self.kwargs['artifacts_handler'] = self.artifacts_handler
        self.kwargs['finished_callback'] = self.finished_callback

        ansible_runner.interface.run(**self.kwargs)

        # FIXME: do cleanup on the tempdir

    def status_handler(self, status, runner_config):
        self._output.write(json.dumps(status).encode('utf-8'))
        self._output.write(b'\n')
        self._output.flush()

    def event_handler(self, event_data):
        self._output.write(json.dumps(event_data).encode('utf-8'))
        self._output.write(b'\n')
        self._output.flush()

    def artifacts_handler(self, artifact_dir):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for dirpath, dirs, files in os.walk(artifact_dir):
                relpath = os.path.relpath(dirpath, artifact_dir)
                if relpath == ".":
                    relpath = ""
                for fname in files:
                    archive.write(os.path.join(dirpath, fname), arcname=os.path.join(relpath, fname))
            archive.close()

        payload = buf.getvalue()

        self._output.write(json.dumps({'artifacts': len(payload)}).encode('utf-8'))
        self._output.write(b'\n')
        self._output.write(payload)
        self._output.flush()

    def finished_callback(self, runner_obj):
        self._output.write(json.dumps({'eof': True}).encode('utf-8'))
        self._output.write(b'\n')
        self._output.flush()
        self._output.close()


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
            elif 'artifacts' in data:
                self.artifacts_callback(self._input.read(data['artifacts']))
            elif 'eof' in data:
                break
            else:
                self.event_callback(data)

        if self.finished_callback is not None:
            self.finished_callback(self)
        return self.status, self.rc
