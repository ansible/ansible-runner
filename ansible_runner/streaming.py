import io
import json
import os
import zipfile


class StreamWorker(object):
    def __init__(self, control_out):
        self.control_out = control_out

    def status_handler(self, status):
        json.dump(status, self.control_out)
        self.control_out.flush()

    def event_handler(self, event_data):
        json.dump(event_data, self.control_out)
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

        self.control_out.write(buf.getvalue())
        self.control_out.flush()
        self.control_out.close()
