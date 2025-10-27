import os

from ansible_runner.config.runner import RunnerConfig
from ansible_runner.streaming import Processor


class TestProcessor:

    def test_artifact_dir_with_int_ident(self, tmp_path):
        kwargs = {
            'private_data_dir': str(tmp_path),
            'ident': 123,
        }
        rc = RunnerConfig(**kwargs)
        p = Processor(rc)
        assert p.artifact_dir == os.path.join(kwargs['private_data_dir'],
                                              'artifacts',
                                              str(kwargs['ident']))
