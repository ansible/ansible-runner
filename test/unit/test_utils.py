import os
import stat

from ansible_runner.utils import cleanup_artifact_dir, dump_artifact


def test_artifact_permissions(tmp_path):
    """Artifacts should allow user read/write"""
    filename = dump_artifact("artifact content", str(tmp_path))
    file_mode = stat.S_IMODE(os.stat(filename).st_mode)
    user_rw = stat.S_IRUSR | stat.S_IWUSR
    assert (user_rw & file_mode) == user_rw, "file mode is incorrect"


def test_cleanup_artifact_dir_only_counts_directories(tmp_path):
    artifact_dir = tmp_path / 'artifacts'
    artifact_dir.mkdir()
    marker = artifact_dir / '.gitkeep'
    marker.touch()
    old = artifact_dir / 'old'
    old.mkdir()
    new = artifact_dir / 'new'
    new.mkdir()
    unrelated = tmp_path / 'unrelated'
    unrelated.mkdir()
    link = artifact_dir / 'linked'
    link.symlink_to(unrelated, target_is_directory=True)
    os.utime(marker, (0, 0))
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))

    cleanup_artifact_dir(str(artifact_dir), num_keep=1)

    assert set(artifact_dir.iterdir()) == {marker, new, link}
    assert unrelated.is_dir()
