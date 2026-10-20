# pylint: disable=R0914

import io
import shutil
import time
import tempfile
import zipfile
import os
import json
import sys
import stat
from pathlib import Path

from .base64io import Base64IO


def stream_dir(source_directory: str, stream: io.FileIO) -> None:
    with tempfile.NamedTemporaryFile() as tmp:
        with zipfile.ZipFile(
            tmp.name, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True, strict_timestamps=False
        ) as archive:
            if source_directory:
                for dirpath, dirs, files in os.walk(source_directory):
                    relpath = os.path.relpath(dirpath, source_directory)
                    if relpath == ".":
                        relpath = ""
                    for fname in files + dirs:
                        full_path = os.path.join(dirpath, fname)
                        # Magic to preserve symlinks
                        if os.path.islink(full_path):
                            archive_relative_path = os.path.relpath(dirpath, source_directory)
                            file_relative_path = os.path.join(archive_relative_path, fname)
                            zip_info = zipfile.ZipInfo(file_relative_path)
                            zip_info.create_system = 3
                            permissions = 0o777
                            permissions |= 0xA000
                            zip_info.external_attr = permissions << 16
                            archive.writestr(zip_info, os.readlink(full_path))
                        elif stat.S_ISFIFO(os.stat(full_path).st_mode):
                            # skip any pipes, as python hangs when attempting
                            # to open them.
                            # i.e. ssh_key_data that was never cleaned up
                            continue
                        else:
                            archive.write(
                                os.path.join(dirpath, fname), arcname=os.path.join(relpath, fname)
                            )
            archive.close()

        zip_size = Path(tmp.name).stat().st_size

        with open(tmp.name, "rb") as source:
            if stream.name == "<stdout>":
                target = sys.stdout.buffer
            else:
                target = stream
            target.write(json.dumps({"zipfile": zip_size}).encode("utf-8") + b"\n")
            target.flush()
            with Base64IO(target) as encoded_target:
                for line in source:
                    encoded_target.write(line)


def _is_within_directory(parent: str, child: str) -> bool:
    """Return True iff child resolves to a path inside parent (or equal to it).
    Uses ``os.path.realpath`` on both sides so the comparison reflects what
    ``open``/``os.symlink`` would actually do on disk (symlinks resolved,
    ``..`` normalized).
    """
    parent_abs = os.path.realpath(parent)
    child_abs = os.path.realpath(child)
    if child_abs == parent_abs:
        return True
    return child_abs.startswith(parent_abs + os.sep)


def _remove_links(links: list[tuple[str, str]]) -> None:
    """Unlink every symbolic link an extraction created, for use when that
    extraction is refused. Whether a link escapes is a property of the whole
    set of links rather than of any one of them, so none of them is trusted
    once one is refused, and leaving attacker-chosen links behind in a
    half-written destination hands the same primitive to whatever reuses it.

    Last created first: an earlier link can be the parent of a later one, and
    ``islink()`` is simply False for a path whose parent has already gone away.
    """
    for out_path, _ in reversed(links):
        if os.path.islink(out_path):
            os.remove(out_path)


def unstream_dir(stream: io.FileIO, length: int, target_directory: str) -> None:
    # NOTE: caller needs to process exceptions
    with tempfile.NamedTemporaryFile() as tmp:
        with open(tmp.name, "wb") as target:
            with Base64IO(stream) as source:
                remaining = length
                chunk_size = 1024 * 1000  # 1 MB
                while remaining != 0:
                    chunk_size = min(chunk_size, remaining)

                    data = source.read(chunk_size)
                    target.write(data)

                    remaining -= chunk_size

        # Snapshot the realpath of the destination once. We use it to bound
        # every member, link target and ancestor we touch below.
        target_root = os.path.realpath(target_directory)

        with zipfile.ZipFile(tmp.name, "r") as archive:
            # Members are written out by hand rather than through
            # ZipFile.extract() for two reasons. It lets us preserve permissions
            # and symlinks -- AWX relies on the execution bit, in particular,
            # for inventory. And it means the path we validate below is exactly
            # the path we open: extract() sanitizes member names by *dropping*
            # ".." components rather than resolving them, so any path predicted
            # for it can name a different file than the one it really writes.
            created_links: list[tuple[str, str]] = []

            for info in archive.infolist():
                out_path = os.path.normpath(os.path.join(target_root, info.filename))
                parent = os.path.dirname(out_path)

                # realpath() resolves every symlink along the way, so this one
                # check covers both ".." escapes in the member name and members
                # whose parent is, or sits beneath, a symlink leading out of the
                # destination -- whether planted by an earlier member of this
                # archive or already present in a reused private_data_dir.
                if not _is_within_directory(target_root, parent):
                    _remove_links(created_links)
                    raise zipfile.BadZipFile(
                        f"Refusing to extract member that escapes target directory: {info.filename!r}"
                    )

                perms = info.external_attr >> 16
                mode = stat.filemode(perms)

                is_symlink = mode[:1] == 'l'
                # lexists(), so that a broken symlink is seen and replaced
                # rather than written through to wherever it points.
                if os.path.lexists(out_path):
                    if is_symlink or os.path.islink(out_path):
                        os.remove(out_path)
                    elif stat.S_ISFIFO(os.stat(out_path).st_mode):
                        # remove any pipes, as python hangs when attempting
                        # to open them.
                        # i.e. ssh_key_data that was never cleaned up
                        os.remove(out_path)
                        continue
                    elif os.path.isdir(out_path):
                        # Special case, the important dirs were pre-created so don't try to chmod them
                        continue

                if info.is_dir():
                    os.makedirs(out_path, exist_ok=True)
                elif is_symlink:
                    # Read the target out of the archive rather than off disk,
                    # and record the link instead of checking it here: where a
                    # link points is not settled until every member is written.
                    link = archive.read(info).decode()
                    os.makedirs(parent, exist_ok=True)
                    os.symlink(link, out_path)
                    created_links.append((out_path, link))
                    # The mode and timestamps belong to the link target, which
                    # may legitimately not exist yet (or at all).
                    continue
                else:
                    os.makedirs(parent, exist_ok=True)
                    with archive.open(info) as source, open(out_path, "wb") as dest:
                        shutil.copyfileobj(source, dest)

                # Fancy logic to preserve modification times
                # AWX uses modification times to determine if new facts were written for a host
                # https://stackoverflow.com/questions/9813243/extract-files-from-zip-file-and-retain-mod-date
                date_time = time.mktime(info.date_time + (0, 0, -1))
                os.utime(out_path, times=(date_time, date_time))
                os.chmod(out_path, perms)

            # Only now is the tree final, and only now does resolving a link
            # say where it really points. Checking each link as it is created
            # is order dependent: "artifacts -> project/../other_job" resolves
            # inside the destination while "project" does not exist yet, and
            # outside it the moment a later "project -> ." lands. Links left by
            # an earlier transfer are checked too, since they compose the same
            # way. Nothing was written *through* an escaping link in the
            # meantime; the parent check above saw to that.
            for dirpath, dirnames, filenames in os.walk(target_root, followlinks=False):
                for name in dirnames + filenames:
                    path = os.path.join(dirpath, name)
                    if os.path.islink(path) and not _is_within_directory(target_root, path):
                        # Read the target before the cleanup unlinks it.
                        link = os.readlink(path)
                        _remove_links(created_links)
                        raise zipfile.BadZipFile(
                            f"Refusing to create symbolic link that escapes target directory: "
                            f"{path!r} -> {link!r}"
                        )
