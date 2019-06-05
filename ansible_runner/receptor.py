import asyncio
import functools
import json
from .interface import run_async


class RunnerMessageIter(asyncio.Queue):

    def __init__(self, *args, **kwargs):
        self.done = False
        super().__init__(*args, **kwargs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.done:
            raise StopAsyncIteration
        return await self.get()

    def event_handler(self, event):
        self._loop.create_task(self.put(json.dumps(event)))

    def status_handler(self, status, runner_config):
        self._loop.create_task(self.put(json.dumps(status)))

    def finished_callback(self, runner_obj):
        self.done = True
        self._loop.create_task(self.put(json.dumps(dict(status="exiting"))))


def execute(message):
    print("Runner Receptor: {}".format(message.raw_payload))
    loop = asyncio.get_event_loop()
    message_iter = RunnerMessageIter(loop=loop)
    loop.call_soon(functools.partial(run_async,
                                     event_handler=message_iter.event_handler,
                                     status_handler=message_iter.status_handler,
                                     **json.loads(message.raw_payload)))
    return message_iter
