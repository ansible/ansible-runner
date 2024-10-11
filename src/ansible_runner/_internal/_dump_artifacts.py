from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import tempfile

from collections.abc import MutableMapping

from ansible_runner.config.runner import RunnerConfig
from ansible_runner.utils import isinventory, isplaybook


def dump_artifacts(config: RunnerConfig) -> None:
    """Introspect the arguments and dump objects to disk"""
    if config.role:
        role = {'name': config.role}
        if config.role_vars:
            role['vars'] = config.role_vars

        hosts = config.host_pattern or 'all'
        play = [{'hosts': hosts, 'roles': [role]}]

        if config.role_skip_facts:
            play[0]['gather_facts'] = False

        config.playbook = play

        if config.envvars is None:
            config.envvars = {}

        roles_path = config.roles_path
        if not roles_path:
            roles_path = os.path.join(config.private_data_dir, 'roles')
        else:
            roles_path += f":{os.path.join(config.private_data_dir, 'roles')}"

        config.envvars['ANSIBLE_ROLES_PATH'] = roles_path

    playbook = config.playbook
    if playbook:
        # Ensure the play is a list of dictionaries
        if isinstance(playbook, MutableMapping):
            playbook = [playbook]

        if isplaybook(playbook):
            path = os.path.join(config.private_data_dir, 'project')
            config.playbook = dump_artifact(json.dumps(playbook), path, 'main.json')

    obj = config.inventory
    if obj and isinventory(obj):
        path = os.path.join(config.private_data_dir, 'inventory')
        if isinstance(obj, MutableMapping):
            config.inventory = dump_artifact(json.dumps(obj), path, 'hosts.json')
        elif isinstance(obj, str):
            if not os.path.exists(os.path.join(path, obj)):
                config.inventory = dump_artifact(obj, path, 'hosts')
            elif os.path.isabs(obj):
                config.inventory = obj
            else:
                config.inventory = os.path.join(path, obj)

    if not config.suppress_env_files:
        for key in ('envvars', 'extravars', 'passwords', 'settings'):
            obj = getattr(config, key, None)
            if obj and not os.path.exists(os.path.join(config.private_data_dir, 'env', key)):
                path = os.path.join(config.private_data_dir, 'env')
                dump_artifact(json.dumps(obj), path, key)

        for key in ('ssh_key', 'cmdline'):
            obj = getattr(config, key, None)
            if obj and not os.path.exists(os.path.join(config.private_data_dir, 'env', key)):
                path = os.path.join(config.private_data_dir, 'env')
                dump_artifact(obj, path, key)


def dump_artifact(obj: str,
                  path: str,
                  filename: str | None = None
                  ) -> str:
    """Write the artifact to disk at the specified path

    :param str obj: The string object to be dumped to disk in the specified
        path. The artifact filename will be automatically created.
    :param str path: The full path to the artifacts data directory.
    :param str filename: The name of file to write the artifact to.
        If the filename is not provided, then one will be generated.

    :return: The full path filename for the artifact that was generated.
    """
    if not os.path.exists(path):
        os.makedirs(path, mode=0o700)

    p_sha1 = hashlib.sha1()
    p_sha1.update(obj.encode(encoding='UTF-8'))

    if filename is None:
        _, fn = tempfile.mkstemp(dir=path)
    else:
        fn = os.path.join(path, filename)

    if os.path.exists(fn):
        c_sha1 = hashlib.sha1()
        with open(fn) as f:
            contents = f.read()
        c_sha1.update(contents.encode(encoding='UTF-8'))

    if not os.path.exists(fn) or p_sha1.hexdigest() != c_sha1.hexdigest():
        lock_fp = os.path.join(path, '.artifact_write_lock')
        lock_fd = os.open(lock_fp, os.O_RDWR | os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR)
        fcntl.lockf(lock_fd, fcntl.LOCK_EX)

        try:
            with open(fn, 'w') as f:
                os.chmod(fn, stat.S_IRUSR | stat.S_IWUSR)
                f.write(str(obj))
        finally:
            fcntl.lockf(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            os.remove(lock_fp)

    return fn
