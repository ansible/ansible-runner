# pylint: disable=R0914

import io
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


def unstream_dir(stream: io.FileIO, length: int, target_directory: str) -> None:
    # NOTE: caller needs to process exceptions
    target_base = os.path.realpath(target_directory)

    def _confine_member(filename: str) -> str:
        """Return the sanitized destination path for an archive member.

        Rejects members whose normalized path escapes ``target_directory`` (a ``..``
        segment in the member name must not reach outside, as the raw name is used
        for ``os.utime``/``os.chmod``), and members that would be written through a
        symlink created by an earlier member of the same archive.
        """
        dest = os.path.normpath(os.path.join(target_base, filename))
        if os.path.commonpath([target_base, dest]) != target_base:
            raise ValueError(f"unsafe path in archive member: {filename!r}")
        parent = os.path.dirname(dest)
        if os.path.commonpath([target_base, os.path.realpath(parent)]) != target_base:
            raise ValueError(f"unsafe path in archive member: {filename!r}")
        return dest

    def _check_link_target(dest: str, link: str) -> None:
        """Reject a symlink whose target is absolute or resolves outside target_directory."""
        if os.path.isabs(link):
            raise ValueError(f"absolute symlink target in archive member: {link!r}")
        resolved = os.path.realpath(os.path.join(os.path.dirname(dest), link))
        if os.path.commonpath([target_base, resolved]) != target_base:
            raise ValueError(f"symlink target escapes target_directory: {link!r}")

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

        with zipfile.ZipFile(tmp.name, "r") as archive:
            # Fancy extraction in order to preserve permissions
            # AWX relies on the execution bit, in particular, for inventory
            # https://www.burgundywall.com/post/preserving-file-perms-with-python-zipfile-module
            for info in archive.infolist():
                out_path = _confine_member(info.filename)

                perms = info.external_attr >> 16
                mode = stat.filemode(perms)

                is_symlink = mode[:1] == 'l'
                link = None
                if is_symlink:
                    # Read and validate the link target before touching target_directory.
                    link = archive.read(info).decode()
                    _check_link_target(out_path, link)
                if os.path.exists(out_path):
                    if is_symlink:
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

                archive.extract(info.filename, path=target_base)

                # Fancy logic to preserve modification times
                # AWX uses modification times to determine if new facts were written for a host
                # https://stackoverflow.com/questions/9813243/extract-files-from-zip-file-and-retain-mod-date
                date_time = time.mktime(info.date_time + (0, 0, -1))
                os.utime(out_path, times=(date_time, date_time))

                if is_symlink:
                    os.remove(out_path)
                    os.symlink(link, out_path)
                else:
                    os.chmod(out_path, perms)
