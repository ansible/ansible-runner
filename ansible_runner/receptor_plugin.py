import logging
import json
import os
import time
import io
import tarfile
import tempfile
import uuid
import asyncio

try:
    import receptor
    from receptor.config import ReceptorConfig
    from receptor.controller import Controller
    receptor_import = True
except ImportError:
    receptor_import = False


from ansible_runner import run


logger = logging.getLogger(__name__)


class Receptor_Runner_Result:

    def __init__(self):
        self.rc = None


class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return obj.hex
        return json.JSONEncoder.default(self, obj)


def run_via_receptor(receptor_node, receptor_peer, receptor_node_id, run_options):

    async def read_responses():
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
                    if 'event_handler' in run_options and run_options['event_handler']:
                        run_options['event_handler'](data)
                    if 'stdout' in data and data['stdout']:
                        print(data['stdout'])
                elif c_type == 'status':
                    data = content[1]
                    if 'status_handler' in run_options and run_options['status_handler']:
                        run_options['status_handler'](data, None)
                elif c_type == 'error':
                    print("Error from remote:", content[1])

    async def run_func():
        if receptor_node_id != receptor_node:
            add_peer_task = controller.add_peer(receptor_peer)
            start_wait = time.time()
            while True:
                if add_peer_task and add_peer_task.done() and not add_peer_task.result():
                    return False
                if controller.receptor.router.node_is_known(receptor_node):
                    break
                if time.time() - start_wait > 5:
                    if not add_peer_task.done():
                        add_peer_task.cancel()
                    return False
                await asyncio.sleep(0.1)
        await controller.send(payload=tmpf.name, recipient=receptor_node, directive='ansible_runner:execute')
        await controller.loop.create_task(read_responses())

    remote_options = {key: value for key, value in run_options.items() if key in (
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
    )}

    with tempfile.NamedTemporaryFile(suffix='.tgz') as tmpf:

        # Create tar file
        with tarfile.open(fileobj=tmpf, mode='w:gz') as tar:
            if 'private_data_dir' in run_options:
                tar.add(run_options['private_data_dir'], arcname='')
            kwargs = json.dumps(remote_options, cls=UUIDEncoder)
            ti = tarfile.TarInfo('kwargs')
            ti.size = len(kwargs)
            ti.mtime = time.time()
            tar.addfile(ti, io.BytesIO(kwargs.encode('utf-8')))
        tmpf.flush()

        # Run the job via Receptor
        if receptor_node_id:
            receptor_args = f"--node-id {receptor_node_id} node --server-disable".split()
        else:
            receptor_args = "node --server-disable".split()
        config = ReceptorConfig(receptor_args)
        config._is_ephemeral = True
        controller = Controller(config)
        controller.run(run_func)
        controller.cleanup_tmpdir()

        res = Receptor_Runner_Result()
        res.rc = 0
        return res

# We set these parameters locally rather than using receptor.plugin_utils
# because this still needs to parse even when our import of receptor failed.
def receptor_plugin_export(func):
    if receptor_import:
        func.receptor_export = True
        func.payload_type = receptor.BUFFER_PAYLOAD
    return func

@receptor_plugin_export
def execute(message, config, result_queue):
    private_dir = None
    try:
        private_dir = tempfile.TemporaryDirectory()
        with tarfile.open(fileobj=message.fp, mode='r:gz') as tar:
            tar.extractall(path=private_dir.name)

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

        run(**kwargs)

    except Exception as exc:
        logger.exception(exc)
        result_queue.put(json.dumps([{'type': 'error'}, str(exc)]))

    finally:
        if private_dir:
            private_dir.cleanup()
