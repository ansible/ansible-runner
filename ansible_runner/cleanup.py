import glob
import subprocess
import shutil
import os
import signal

from ansible_runner.defaults import registry_auth_prefix


__all__ = ['add_cleanup_args', 'run_cleanup']


def add_cleanup_args(command):
    command.add_argument(
        "--file-pattern",
        help="A file glob pattern to find private_data_dir folders to remove. "
             "Example: --file-pattern=/tmp/.ansible-runner-*"
    )
    command.add_argument(
        "--exclude-idents",
        help="A comma separated list of run IDs to preserve. "
             "This will only work if the deletion pattern contains the {ident} syntax."
    )
    command.add_argument(
        "--remove-images",
        help="A comma separated list of podman or docker tags to delete. "
             "This may not remove the corresponding layers, use the image-prune option to assure full deletion. "
             "Example: --remove-images=quay.io/user/image:devel,quay.io/user/builder:latest"
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


def run_command(cmd):
    '''Given list cmd, runs command and returns standard out, expecting success'''
    process = subprocess.run(cmd, capture_output=True)
    stdout = str(process.stdout, encoding='utf-8')
    if process.returncode != 0:
        print('Error running command:')
        print(' '.join(cmd))
        print('Stdout:')
        print(stdout)
        raise RuntimeError('Error running command')
    print('Successfully ran command: {}'.format(' '.join(cmd)))
    print(stdout)
    # import pdb; pdb.set_trace()
    return stdout.strip()


def is_alive(dir):
    pidfile = os.path.join(dir, 'pid')

    try:
        with open(pidfile, 'r') as f:
            pid = int(f.readline())
    except IOError:
        return False

    try:
        os.kill(pid, signal.SIG_DFL)
        return(0)
    except OSError:
        return(1)


def cleanup_dirs(pattern, exclude_idents=()):
    discovered_dirs = glob.glob(pattern)
    ct = 0
    running_idents = []
    for dir in discovered_dirs:
        if any(ident in dir for ident in exclude_idents):
            continue
        if is_alive(dir):
            running_idents.extend(os.path.listdir(os.path.join(dir, 'artifacts')))
            continue
        shutil.rmtree(dir)
        print(f'Removed directory {dir}')
        ct += 1
    if running_idents:
        print(f'Excluding from cleanup running jobs {running_idents}')
    registry_auth_pattern = f'{registry_auth_prefix}{{ident}}_**'
    registry_auth_dirs = glob.glob(registry_auth_pattern)
    for dir in registry_auth_dirs:
        if any(ident in dir for ident in exclude_idents) or any(ident in dir for ident in running_idents):
            continue
        shutil.rmtree(dir)
        print(f'Removed associated registry auth dir {dir}')
    return ct


def cleanup_images(images, runtime='podman'):
    """Note: docker will just untag while podman will remove layers with same command"""
    rm_ct = 0
    for image_tag in images:
        stdout = run_command([runtime, 'images', '--format="{{.Repository}}:{{.Tag}}"', image_tag])
        if not stdout:
            continue
        for discovered_tag in stdout.split('\n'):
            stdout = run_command([runtime, 'rmi', discovered_tag.strip().strip('"'), '-f'])
            rm_ct += stdout.count('Untagged:')
    return rm_ct


def prune_images(runtime='podman'):
    """Run the prune images command and return changed status"""
    stdout = run_command([runtime, 'image', 'prune', '-f'])
    if not stdout or stdout == "Total reclaimed space: 0B":
        return False
    return True


def comma_sep_parse(vargs, key):
    if vargs.get(key):
        return vargs.get(key).split(',')
    return []


def run_cleanup(vargs):
    exclude_idents = comma_sep_parse(vargs, 'exclude_idents')
    remove_images = comma_sep_parse(vargs, 'remove_images')
    dir_ct = image_ct = 0
    pruned = False

    if vargs.get('file_pattern'):
        dir_ct = cleanup_dirs(vargs.get('file_pattern'), exclude_idents=exclude_idents)

    if remove_images:
        image_ct = cleanup_images(remove_images, runtime=vargs.get('process_isolation_executable'))

    if vargs.get('image_prune'):
        pruned = prune_images(runtime=vargs.get('process_isolation_executable'))

    if dir_ct or image_ct or pruned:
        print('(changed: True)')
    else:
        print('(changed: False)')
