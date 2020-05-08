import logging
import json
import os
import time
import io
import zipfile
import tempfile
import uuid
import asyncio

import ansible_runner.interface

try:
    import receptor
    from receptor.config import ReceptorConfig
    from receptor.controller import Controller
    receptor_import = True
except ImportError:
    receptor_import = False

logger = logging.getLogger(__name__)


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return obj.hex
        return json.JSONEncoder.default(self, obj)


# List of kwargs options to the run method that should be sent to the remote executor.
remote_run_options = (
    'forks',
    'host_pattern',
    'ident',
    'ignore_logging',
    'inventory',
    'limit',
    'module',
    'module_args',
    'omit_event_data',
    'only_failed_event_data',
    'playbook',
    'verbosity',
)


def run_via_receptor(via_receptor, receptor_peer, receptor_node_id, run_options):

    async def read_responses():
        event_handler = run_options.get('event_handler', None)
        status_handler = run_options.get('status_handler', None)
        while True:
            message = await controller.recv()
            if message.header.get("eof", False):
                break
            elif message.payload:
                content = json.loads(message.payload.readall())
                c_header = content[0]
                c_type = c_header['type']
                if c_type == 'event':
                    data = content[1]
                    if event_handler:
                        event_handler(data)
                    if 'stdout' in data and data['stdout']:
                        print(data['stdout'])
                elif c_type == 'status':
                    data = content[1]
                    if status_handler:
                        status_handler(data, None)
                elif c_type == 'error':
                    result.errored = True
                    print("Error from remote:", content[1])

    async def run_func():
        if receptor_node_id != via_receptor:
            add_peer_task = controller.add_peer(receptor_peer)
            start_wait = time.time()
            while True:
                if add_peer_task and add_peer_task.done() and not add_peer_task.result():
                    raise RuntimeError('Cannot connect to peer')
                if controller.receptor.router.node_is_known(via_receptor):
                    break
                if time.time() - start_wait > 5:
                    if not add_peer_task.done():
                        add_peer_task.cancel()
                    raise RuntimeError('Timed out waiting for peer')
                await asyncio.sleep(0.1)
        await controller.send(payload=tmpf.name, recipient=via_receptor, directive='ansible_runner:execute')
        await controller.loop.create_task(read_responses())

    if not receptor_peer:
        receptor_peer = 'receptor://localhost'
    remote_options = {key: value for key, value in run_options.items() if key in remote_run_options}

    with tempfile.NamedTemporaryFile() as tmpf:

        # Create archive
        with zipfile.ZipFile(tmpf, 'w') as zip:
            private_data_dir = run_options.get('private_data_dir', None)
            if private_data_dir:
                for dirpath, dirs, files in os.walk(private_data_dir):
                    relpath = os.path.relpath(dirpath, private_data_dir)
                    if relpath == ".":
                        relpath = ""
                    for file in files:
                        zip.write(os.path.join(dirpath, file), arcname=os.path.join(relpath, file))
            kwargs = json.dumps(remote_options, cls=UUIDEncoder)
            zip.writestr('kwargs', kwargs)
            zip.close()
        tmpf.flush()

        # Run the job via Receptor
        if receptor_node_id:
            receptor_args = f"--node-id {receptor_node_id} node --server-disable".split()
        else:
            receptor_args = "node --server-disable".split()
        config = ReceptorConfig(receptor_args)
        config._is_ephemeral = True
        controller = Controller(config)
        try:
            result = type('Receptor_Runner_Result', (), {'rc': 0, 'errored': False})
            controller.run(run_func)
        except Exception as exc:
            result.errored = True
            setattr(result, 'exception', exc)
            print(str(exc))
        finally:
            controller.cleanup_tmpdir()

        return result


# We set these parameters locally rather than using receptor.plugin_utils
# because this still needs to parse even when our import of receptor failed.
def receptor_plugin_export(func):
    if receptor_import:
        func.receptor_export = True
        func.payload_type = receptor.FILE_PAYLOAD
    return func


@receptor_plugin_export
def execute(message, config, result_queue):
    private_dir = None
    try:
        private_dir = tempfile.TemporaryDirectory()
        with zipfile.ZipFile(message, 'r') as zip:
            zip.extractall(path=private_dir.name)

        kwargs_path = os.path.join(private_dir.name, 'kwargs')
        if os.path.exists(kwargs_path):
            with open(kwargs_path, "r") as kwf:
                kwargs = json.load(kwf)
            if not isinstance(kwargs, dict):
                raise ValueError("Invalid kwargs data")
        else:
            kwargs = dict()

        kwargs["quiet"] = True
        kwargs["private_data_dir"] = private_dir.name
        kwargs["event_handler"] = lambda item: result_queue.put(json.dumps([{'type': 'event'}, item]))
        kwargs["status_handler"] = lambda item, runner_config: result_queue.put(json.dumps([{'type': 'status'}, item]))
        kwargs["finished_callback"] = lambda runner: result_queue.put(json.dumps([{'type': 'finished'}]))

        ansible_runner.interface.run(**kwargs)

    except Exception as exc:
        logger.exception(exc)
        result_queue.put(json.dumps([{'type': 'error'}, str(exc)]))

    finally:
        if private_dir:
            private_dir.cleanup()
