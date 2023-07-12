import os

from ansible_runner.streaming import Processor


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
