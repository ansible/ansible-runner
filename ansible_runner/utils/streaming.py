import time
import tempfile
import zipfile
import os
import json
import sys
import stat

from .base64io import Base64IO
from pathlib import Path


def stream_dir(source_directory, stream):
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


def unstream_dir(stream, length, target_directory):
    # NOTE: caller needs to process exceptions
    with tempfile.NamedTemporaryFile() as tmp:
        with open(tmp.name, "wb") as target:
            with Base64IO(stream) as source:
                remaining = length
                chunk_size = 1024 * 1000  # 1 MB
                while remaining != 0:
                    if chunk_size >= remaining:
                        chunk_size = remaining

                    data = source.read(chunk_size)
                    target.write(data)

                    remaining -= chunk_size

        with zipfile.ZipFile(tmp.name, "r") as archive:
            # Fancy extraction in order to preserve permissions
            # AWX relies on the execution bit, in particular, for inventory
            # https://www.burgundywall.com/post/preserving-file-perms-with-python-zipfile-module
            for info in archive.infolist():
                out_path = os.path.join(target_directory, info.filename)

                perms = info.external_attr >> 16
                mode = stat.filemode(perms)

                is_symlink = mode[:1] == 'l'
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

                archive.extract(info.filename, path=target_directory)

                # Fancy logic to preserve modification times
                # AWX uses modification times to determine if new facts were written for a host
                # https://stackoverflow.com/questions/9813243/extract-files-from-zip-file-and-retain-mod-date
                date_time = time.mktime(info.date_time + (0, 0, -1))
                os.utime(out_path, times=(date_time, date_time))

                if is_symlink:
                    link = open(out_path).read()
                    os.remove(out_path)
                    os.symlink(link, out_path)
                else:
                    os.chmod(out_path, perms)
