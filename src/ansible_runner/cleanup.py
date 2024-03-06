from __future__ import annotations

import argparse
import datetime
import glob
import os
import signal
import subprocess
import sys

from pathlib import Path
from tempfile import gettempdir

from ansible_runner.defaults import (
    GRACE_PERIOD_DEFAULT,
    registry_auth_prefix,
    default_process_isolation_executable
)
from ansible_runner.utils import cleanup_folder


__all__ = ['add_cleanup_args', 'run_cleanup']


def add_cleanup_args(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--file-pattern",
        help="A file glob pattern to find private_data_dir folders to remove. "
             "Example: --file-pattern=/tmp/.ansible-runner-*"
    )
    command.add_argument(
        "--exclude-strings",
        nargs='*',
        help="A comma separated list of keywords in directory name or path to avoid deleting."
    )
    command.add_argument(
        "--remove-images",
        nargs='*',
        help="A comma separated list of podman or docker tags to delete. "
             "This may not remove the corresponding layers, use the image-prune option to assure full deletion. "
             "Example: --remove-images=quay.io/user/image:devel quay.io/user/builder:latest"
    )
    command.add_argument(
        "--grace-period",
        default=GRACE_PERIOD_DEFAULT,
        type=int,
        help="Time (in minutes) after last modification to exclude a folder from deletion for. "
             "This is to avoid deleting folders that were recently created, or folders not started via the start command. "
             "Value of 0 indicates that no folders will be excluded based on modified time."
    )
    command.add_argument(
        "--image-prune",
        action="store_true",
        help="If specified, will run docker / podman image prune --force. "
             "This will only run after untagging."
    )
    command.add_argument(
        "--process-isolation-executable",
        default="podman",
        help="The container image to clean up images for (default=podman)"
    )


def run_command(cmd: list) -> str:
    '''Given list cmd, runs command and returns standard out, expecting success'''
    process = subprocess.run(cmd, capture_output=True, check=False)
    stdout = str(process.stdout, encoding='utf-8')
    if process.returncode != 0:
        print('Error running command:')
        print(' '.join(cmd))
        print('Stdout:')
        print(stdout)
        raise RuntimeError('Error running command')
    return stdout.strip()


def is_alive(directory: str) -> int:
    pidfile = os.path.join(directory, 'pid')

    try:
        with open(pidfile, 'r') as f:
            pid = int(f.readline())
    except IOError:
        return 0

    try:
        os.kill(pid, signal.SIG_DFL)
        return 0
    except OSError:
        return 1


def project_idents(directory: str) -> list:
    """Given directory, give list of idents that we have artifacts for"""
    try:
        return os.listdir(os.path.join(directory, 'artifacts'))
    except (FileNotFoundError, NotADirectoryError):
        return []


def delete_associated_folders(directory: str) -> None:
    """Where directory is the private_data_dir for a completed job, this deletes related tmp folders it used"""
    for ident in project_idents(directory):
        registry_auth_pattern = f'{gettempdir()}/{registry_auth_prefix}{ident}_*'
        for radir in glob.glob(registry_auth_pattern):
            changed = cleanup_folder(radir)
            if changed:
                print(f'Removed associated registry auth dir {radir}')


def validate_pattern(pattern: str) -> None:
    # do not let user shoot themselves in foot by deleting these important linux folders
    paths = (
        '/', '/bin', '/dev', '/home', '/lib', '/mnt', '/proc',
        '/run', '/sys', '/usr', '/boot', '/etc', '/opt', '/sbin', gettempdir(), '/var'
    )
    prohibited_paths = {Path(s) for s in paths}.union(Path(s).resolve() for s in paths)
    bad_paths = [dir for dir in glob.glob(pattern) if Path(dir).resolve() in prohibited_paths]
    if bad_paths:
        raise RuntimeError(
            f'Provided pattern could result in deleting system folders:\n{" ".join(bad_paths)}\n'
            'Refusing to continue for user system safety.'
        )


def cleanup_dirs(pattern: str, exclude_strings: list | None = None, grace_period: int = GRACE_PERIOD_DEFAULT) -> int:
    if exclude_strings is None:
        exclude_strings = []
    try:
        validate_pattern(pattern)
    except RuntimeError as e:
        sys.exit(str(e))
    ct = 0
    now_time = datetime.datetime.now()
    for directory in glob.glob(pattern):
        if any(str(exclude_string) in directory for exclude_string in exclude_strings):
            continue
        if grace_period:
            st = os.stat(directory)
            modtime = datetime.datetime.fromtimestamp(st.st_mtime)
            if modtime > now_time - datetime.timedelta(minutes=grace_period):
                continue
        if is_alive(directory):
            print(f'Excluding running project {directory} from cleanup')
            continue
        delete_associated_folders(directory)
        changed = cleanup_folder(directory)
        if changed:
            ct += 1

    return ct


def cleanup_images(images: list, runtime: str) -> int:
    """
    `docker rmi` will just untag while
    `podman rmi` will untag and remove layers and cause runing container to be killed
    for podman we use `untag` to achieve the same behavior

    NOTE: this only untag the image and does not delete the image prune_images need to be call to delete
    """
    rm_ct = 0
    for image_tag in images:
        stdout = run_command([runtime, 'images', '--format="{{.Repository}}:{{.Tag}}"', image_tag])
        if not stdout:
            continue
        for discovered_tag in stdout.split('\n'):
            if runtime == 'podman':
                try:
                    stdout = run_command([runtime, 'untag', image_tag])
                    if not stdout:
                        rm_ct += 1
                except Exception:
                    pass  # best effort untag
            else:
                stdout = run_command([runtime, 'rmi', discovered_tag.strip().strip('"'), '-f'])
                rm_ct += stdout.count('Untagged:')
    return rm_ct


def prune_images(runtime: str) -> bool:
    """Run the prune images command and return changed status"""
    stdout = run_command([runtime, 'image', 'prune', '-f'])
    if not stdout or stdout == "Total reclaimed space: 0B":
        return False
    return True


def run_cleanup(vargs: dict) -> None:
    exclude_strings = vargs.get('exclude_strings') or []
    remove_images = vargs.get('remove_images') or []
    file_pattern = vargs.get('file_pattern')
    dir_ct = image_ct = 0
    pruned = False

    if file_pattern:
        dir_ct = cleanup_dirs(file_pattern, exclude_strings=exclude_strings, grace_period=vargs.get('grace_period', GRACE_PERIOD_DEFAULT))
        if dir_ct:
            print(f'Removed {dir_ct} private data dir(s) in pattern {file_pattern}')

    if remove_images:
        image_ct = cleanup_images(remove_images, runtime=vargs.get('process_isolation_executable', default_process_isolation_executable))
        if image_ct:
            print(f'Removed {image_ct} image(s)')

    if vargs.get('image_prune'):
        pruned = prune_images(runtime=vargs.get('process_isolation_executable', default_process_isolation_executable))
        if pruned:
            print('Pruned images')

    if dir_ct or image_ct or pruned:
        print('(changed: True)')
    else:
        print('(changed: False)')
