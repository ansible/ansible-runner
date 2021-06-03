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
            tmp.name, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        ) as archive:
            if source_directory:
                for dirpath, dirs, files in os.walk(source_directory):
                    relpath = os.path.relpath(dirpath, source_directory)
                    if relpath == ".":
                        relpath = ""
                    for fname in files:
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
            # https://www.burgundywall.com/post/preserving-file-perms-with-python-zipfile-module
            for info in archive.infolist():
                out_path = os.path.join(target_directory, info.filename)
                
                perms = info.external_attr >> 16
                mode = stat.filemode(perms)
                
                is_symlink = mode[:1] == 'l'
                if is_symlink and os.path.exists(out_path):
                    os.remove(out_path)
                        
                archive.extract(info.filename, path=target_directory)

                if is_symlink:
                    link = open(out_path).read()
                    os.remove(out_path)
                    os.symlink(link, out_path)
                else:
                    os.chmod(out_path, perms)
