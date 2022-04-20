""" Ensure the generation of container volume mounts is handled
predictably and consistently """

import os
import pytest

from typing import NamedTuple

from ansible_runner.config._base import BaseConfig
from ansible_runner.exceptions import ConfigurationError


class Variation(NamedTuple):
    """one piece of the path"""

    comment: str
    path: str


dir_variations = (
    Variation(comment="dir no slash", path="/somedir_0"),
    Variation(comment="dir with slash", path="/somedir_1/"),
    Variation(comment="nested dir no slash", path="/somedir/otherdir_0"),
    Variation(comment="nested dir with slash", path="/somedir/otherdir_1/"),
    Variation(comment="path with dot", path="/somedir/foo.bar"),
    Variation(comment="path with var no slash", path="$HOME/somedir_0"),
    Variation(comment="path with var slash", path="$HOME/somedir_1"),
    Variation(comment="path with ~ no slash", path="~/somedir_2"),
    Variation(comment="path with ~ slash", path="~/somedir_3"),
)

labels = (None, "", "Z", "ro,Z", ":z")
not_safe = ("/", "/home", "/usr")


def id_for_dst(value):
    """generate a test id for dest"""
    return f"dst->{value.comment}"


def id_for_isdir(value):
    """generate a test id for dest"""
    return f"isdir->{value}"


def id_for_label(value):
    """generate a test id for labels"""
    return f"labels->{value}"


def id_for_src(value):
    """generate a test id for src"""
    return f"src->{value.comment}"


def resolve_path(path):
    """Fully resolve a path"""
    return os.path.abspath(os.path.expanduser(os.path.expandvars(path)))


def generate_volmount_args(src_str, dst_str, labels):
    """Generate a podman style volmount string"""
    vol_mount_str = f"{src_str}:{dst_str}"
    if labels:
        if not labels.startswith(":"):
            vol_mount_str += ":"
        vol_mount_str += labels
    return ["-v", vol_mount_str]


@pytest.mark.parametrize("not_safe", not_safe)
def test_check_not_safe_to_mount_dir(not_safe, mocker):
    """Ensure unsafe directories are not mounted"""
    with pytest.raises(ConfigurationError):
        bc = BaseConfig()
        mocker.patch("os.path.exists", return_value=True)
        bc._update_volume_mount_paths(
            args_list=[], src_mount_path=not_safe, dst_mount_path=None
        )


@pytest.mark.parametrize("not_safe", not_safe)
def test_check_not_safe_to_mount_file(not_safe, mocker):
    """Ensure unsafe directories for a given file are not mounted"""
    file_path = os.path.join(not_safe, "file.txt")
    with pytest.raises(ConfigurationError):
        bc = BaseConfig()
        mocker.patch("os.path.exists", return_value=True)
        bc._update_volume_mount_paths(
            args_list=[], src_mount_path=file_path, dst_mount_path=None
        )


@pytest.mark.parametrize("path", dir_variations, ids=id_for_src)
def test_duplicate_detection_dst(path, mocker):
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.path.isdir", return_value=True)
    """Ensure no duplicate volume mount entries are created"""
    base_config = BaseConfig()

    def generate(args_list):
        for entry in dir_variations:
            for label in labels:
                base_config._update_volume_mount_paths(
                    args_list=first_pass,
                    src_mount_path=path.path,
                    dst_mount_path=entry.path,
                    labels=label,
                )

    first_pass = []
    generate(first_pass)
    second_pass = first_pass[:]
    generate(second_pass)
    assert first_pass == second_pass


@pytest.mark.parametrize("labels", labels, ids=id_for_label)
@pytest.mark.parametrize("path", dir_variations, ids=id_for_src)
def test_no_dst_all_dirs(path, labels, mocker):
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.path.isdir", return_value=True)
    """Ensure dst == src when not provided"""
    src_str = os.path.join(resolve_path(path.path), "")
    dst_str = src_str
    expected = generate_volmount_args(src_str=src_str, dst_str=dst_str, labels=labels)

    result = []
    BaseConfig()._update_volume_mount_paths(
        args_list=result, src_mount_path=path.path, dst_mount_path=None, labels=labels
    )

    explanation = (
        f"provided: {path.path}:{None}",
        f"got: {result}",
        f"expected {expected}",
    )
    assert result == expected, explanation
    assert all(part.endswith('/') for part in result[1].split(':')[0:1]), explanation


@pytest.mark.parametrize("labels", labels, ids=id_for_label)
@pytest.mark.parametrize("dst", dir_variations, ids=id_for_dst)
@pytest.mark.parametrize("src", dir_variations, ids=id_for_src)
def test_src_dst_all_dirs(src, dst, labels, mocker):
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.path.isdir", return_value=True)
    """Ensure src and dest end with trailing slash"""
    src_str = os.path.join(resolve_path(src.path), "")
    dst_str = os.path.join(resolve_path(dst.path), "")
    expected = generate_volmount_args(src_str=src_str, dst_str=dst_str, labels=labels)

    result = []
    BaseConfig()._update_volume_mount_paths(
        args_list=result, src_mount_path=src.path, dst_mount_path=dst.path, labels=labels
    )

    explanation = (
        f"provided: {src.path}:{dst.path}",
        f"got: {result}",
        f"expected {expected}",
    )
    assert result == expected, explanation
    assert all(part.endswith('/') for part in result[1].split(':')[0:1]), explanation


@pytest.mark.parametrize("labels", labels, ids=id_for_label)
@pytest.mark.parametrize("path", dir_variations, ids=id_for_src)
def test_src_dst_all_files(path, labels, mocker):
    """Ensure file paths are transformed correctly into dir paths"""
    src_str = os.path.join(resolve_path(path.path), "")
    dst_str = src_str
    expected = generate_volmount_args(src_str=src_str, dst_str=dst_str, labels=labels)

    result = []
    src_file = os.path.join(path.path, "", "file.txt")
    dest_file = src_file

    base_config = BaseConfig()
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.path.isdir", return_value=False)
    base_config._update_volume_mount_paths(
        args_list=result, src_mount_path=src_file, dst_mount_path=dest_file, labels=labels
    )

    explanation = (
        f"provided: {src_file}:{dest_file}",
        f"got: {result}",
        f"expected {expected}",
    )
    assert result == expected, explanation
    assert all(part.endswith('/') for part in result[1].split(':')[0:1]), explanation


@pytest.mark.parametrize("relative", (".", "..", "../.."))
@pytest.mark.parametrize("labels", labels, ids=id_for_label)
@pytest.mark.parametrize("dst", dir_variations, ids=id_for_dst)
@pytest.mark.parametrize("src", dir_variations, ids=id_for_src)
def test_src_dst_all_relative_dirs(src, dst, labels, relative, mocker):
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("os.path.isdir", return_value=True)
    """Ensure src is resolved and dest mapped to workdir when relative"""
    relative_src = f"{relative}{src.path}"
    relative_dst = f"{relative}{dst.path}"
    workdir = "/workdir"
    src_str = os.path.join(resolve_path(relative_src), "")
    dst_str = os.path.join(resolve_path(os.path.join(workdir, relative_dst)), "")
    expected = generate_volmount_args(src_str=src_str, dst_str=dst_str, labels=labels)

    result = []
    BaseConfig(container_workdir=workdir)._update_volume_mount_paths(
        args_list=result, src_mount_path=relative_src, dst_mount_path=relative_dst, labels=labels
    )

    explanation = (
        f"provided: {relative_src}:{relative_dst}",
        f"got: {result}",
        f"expected {expected}",
    )
    assert result == expected, explanation
    assert all(part.endswith('/') for part in result[1].split(':')[0:1]), explanation
