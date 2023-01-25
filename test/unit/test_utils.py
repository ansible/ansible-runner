import os
import stat

from ansible_runner.utils import dump_artifact


def test_artifact_permissions(tmp_path):
    """Artifacts should allow user read/write"""
    filename = dump_artifact("artifact content", str(tmp_path))
    file_mode = stat.S_IMODE(os.stat(filename).st_mode)
    user_rw = stat.S_IRUSR | stat.S_IWUSR
    assert (user_rw & file_mode) == user_rw, "file mode is incorrect"
