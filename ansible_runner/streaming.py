import base64
import io
import json
import os
import zipfile


class StreamWorker(object):
    def __init__(self, control_out):
        self.control_out = control_out

    def status_handler(self, status, runner_config):
        self.control_out.write(json.dumps(status).encode('utf-8'))
        self.control_out.write(b'\n')
        self.control_out.flush()

    def event_handler(self, event_data):
        self.control_out.write(json.dumps(event_data).encode('utf-8'))
        self.control_out.write(b'\n')
        self.control_out.flush()

    def artifacts_callback(self, artifact_dir):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for dirpath, dirs, files in os.walk(artifact_dir):
                relpath = os.path.relpath(dirpath, artifact_dir)
                if relpath == ".":
                    relpath = ""
                for fname in files:
                    archive.write(os.path.join(dirpath, fname), arcname=os.path.join(relpath, fname))
            archive.close()

        data = {
            'artifacts': True,
            'payload': base64.b64encode(buf.getvalue()).decode('ascii'),
        }
        self.control_out.write(json.dumps(data).encode('utf-8'))
        self.control_out.write(b'\n')
        self.control_out.flush()
        self.control_out.close()
