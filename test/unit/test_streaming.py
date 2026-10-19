import base64
import io
import json
import os
import zipfile

from ansible_runner.streaming import Processor


def _artifact_stream_with_escaping_symlink(escape_target):
    """Frame a zip whose only member is a symlink pointing outside the
    destination, the way a worker streams an artifact directory back.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        info = zipfile.ZipInfo('evil-link')
        info.create_system = 3
        info.external_attr = (0o777 | 0xA000) << 16
        archive.writestr(info, str(escape_target))
    body = buf.getvalue()
    return io.BytesIO(
        json.dumps({'zipfile': len(body)}).encode() + b'\n' + base64.b64encode(body)
    )


class TestProcessor:

    def test_artifact_dir_with_int_ident(self, tmp_path):
        kwargs = {
            'private_data_dir': str(tmp_path),
            'ident': 123,
        }
        p = Processor(**kwargs)
        assert p.artifact_dir == os.path.join(kwargs['private_data_dir'],
                                              'artifacts',
                                              str(kwargs['ident']))

    def test_run_reports_artifact_extraction_failure(self, tmp_path):
        """A refused artifact stream is reported as an error status and still
        runs the normal teardown, rather than raising out of run().
        """
        statuses = []
        finished = []
        processor = Processor(
            _input=_artifact_stream_with_escaping_symlink(tmp_path / 'outside'),
            private_data_dir=str(tmp_path),
            status_handler=lambda data, runner_config: statuses.append(data),
            finished_callback=finished.append,
        )

        status, _ = processor.run()

        assert status == 'error'
        assert finished == [processor]
        explanations = [s.get('job_explanation', '') for s in statuses]
        assert any('Failed to extract artifacts directory' in e for e in explanations)
        assert any('result_traceback' in s for s in statuses)
