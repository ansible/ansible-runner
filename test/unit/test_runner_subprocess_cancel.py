from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from subprocess import TimeoutExpired

from ansible_runner.runner import Runner


def test_subprocess_mode_cancel_callback_kills_container(mocker, tmp_path):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()

    process = mocker.Mock()
    process.pid = 4242
    process.returncode = 0
    process.communicate.side_effect = [
        TimeoutExpired(cmd=["container", "run"], timeout=0.1),
        ("", ""),
    ]

    popen = mocker.patch("ansible_runner.runner.Popen", return_value=process)
    kill_container = mocker.patch.object(Runner, "kill_container")
    handle_termination = mocker.patch.object(Runner, "handle_termination")

    config = SimpleNamespace(
        runner_mode="subprocess",
        directory_isolation_path=None,
        directory_isolation_cleanup=None,
        process_isolation=True,
        process_isolation_path_actual=None,
        containerized=True,
        artifact_dir=str(artifact_dir),
        ident="demo",
        rotate_artifacts=0,
        suppress_output_file=True,
        json_mode=False,
        command=["container", "run"],
        cwd=str(tmp_path),
        env={},
        suppress_ansible_output=False,
        input_fd=None,
        output_fd=None,
        error_fd=None,
        subprocess_timeout=None,
        container_name="ansible_runner_demo",
        process_isolation_executable="container",
    )

    runner = Runner(config=config, cancel_callback=lambda: True)

    status, rc = runner.run()

    assert status == "canceled"
    assert rc == 254
    popen.assert_called_once()
    kill_container.assert_called_once_with()
    handle_termination.assert_called_once_with(4242)
