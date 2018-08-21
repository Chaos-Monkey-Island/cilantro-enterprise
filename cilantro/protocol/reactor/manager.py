import asyncio, os, logging
import zmq.asyncio
from cilantro.logger import get_logger
from cilantro.protocol.reactor.executor import Executor


class ExecutorManager:

    def __init__(self, signing_key, router, name='Worker'):
        self.log = get_logger(name)

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.context = zmq.asyncio.Context()
        self.router = router
        self.executors = {name: executor(loop=self.loop, context=self.context, router=self.router)
                          for name, executor in Executor.registry.items()}

    def start(self):
        try:
            self.loop.run_forever()
        except Exception as e:
            self.log.fatal("Exception running main event loop... error:\n{}".format(e))

        # TODO cleanup in 'finally'?