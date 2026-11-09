"""Regression coverage for rotation deleting the current run (issue #1160)."""
import os
import sys
import time
from pathlib import Path

import pexpect
import pytest

from ansible_runner import Runner
from ansible_runner.config.runner import RunnerConfig
from ansible_runner.utils import cleanup_artifact_dir


@pytest.mark.parametrize('num_keep', [0, 1, 2, 4])
def test_rotation_preserves_current_run_and_retention_limit(tmp_path, num_keep):
    config = RunnerConfig(str(tmp_path), ident='current', rotate_artifacts=num_keep)
    config.command = [sys.executable, '-c', 'print("rotation survived")']
    config.cwd = str(tmp_path)
    config.env = {}
    config.expect_passwords = {pexpect.TIMEOUT: None, pexpect.EOF: None}
    config.suppress_ansible_output = True
    config.pexpect_timeout = 1
    config.pexpect_use_poll = True
    config.job_timeout = 10
    config.idle_timeout = 0
    artifact_root = Path(config.artifact_dir).parent
    previous = []
    # A prior run may acquire a newer mtime through later directory changes.
    # Set explicit mtimes so this regression does not depend on scheduling luck.
    future = time.time() + 3600
    for index in range(3):
        path = artifact_root / f'previous-{index}'
        path.mkdir()
        os.utime(path, (future + index, future + index))
        previous.append(path.name)

    status, exitcode = Runner(config=config).run()

    assert status == 'successful'
    assert exitcode == 0
    assert (Path(config.artifact_dir) / 'stdout').read_text().strip() == 'rotation survived'
    retained = {path.name for path in artifact_root.iterdir()}
    old_keep = len(previous) if num_keep == 0 else min(len(previous), num_keep - 1)
    assert retained == {'current', *previous[len(previous) - old_keep:]}


@pytest.mark.parametrize('path_style', ['absolute', 'relative', 'parent-traversal', 'symlink-parent'])
@pytest.mark.parametrize('num_keep', [0, 1, 2, 4])
def test_cleanup_protects_current_path_aliases(tmp_path, monkeypatch, path_style, num_keep):
    root = tmp_path / 'artifacts'
    root.mkdir()
    current = root / 'current'
    current.mkdir()
    old_names = ['previous-0', 'previous-1', 'previous-2']
    os.utime(current, (100, 100))
    for index, name in enumerate(old_names):
        old = root / name
        old.mkdir()
        os.utime(old, (200 + index, 200 + index))

    parent = str(root)
    protected = str(current)
    if path_style == 'relative':
        monkeypatch.chdir(tmp_path)
        parent, protected = 'artifacts', 'artifacts/current'
    elif path_style == 'parent-traversal':
        parent = str(current / '..')
    elif path_style == 'symlink-parent':
        alias = tmp_path / 'alias'
        alias.symlink_to(root, target_is_directory=True)
        protected = str(alias / 'current')

    cleanup_artifact_dir(parent, num_keep, current_artifact_dir=protected)

    old_keep = len(old_names) if num_keep == 0 else min(len(old_names), num_keep - 1)
    assert {p.name for p in root.iterdir()} == {'current', *old_names[len(old_names) - old_keep:]}


@pytest.mark.parametrize('protected', [None, 'not-present'])
def test_cleanup_without_current_preserves_original_retention(tmp_path, protected):
    for index in range(3):
        path = tmp_path / f'old-{index}'
        path.mkdir()
        os.utime(path, (100 + index, 100 + index))
    current = str(tmp_path / protected) if protected else None

    cleanup_artifact_dir(str(tmp_path), 1, current_artifact_dir=current)

    assert {p.name for p in tmp_path.iterdir()} == {'old-2'}
