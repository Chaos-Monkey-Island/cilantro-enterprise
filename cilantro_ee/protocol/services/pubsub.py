import asyncio

import zmq

from cilantro_ee.protocol.services.core import SocketStruct


class SubscriptionService:
    def __init__(self, ctx: zmq.Context, timeout=100, linger=2000):
        # Socket constants
        self.ctx = ctx
        self.timeout = timeout
        self.linger = linger

        # State variables
        self.subscriptions = {}
        self.running = False

        # Async queues
        self.received = []
        self.to_remove = []

    def add_subscription(self, socket_id: SocketStruct, filter=b''):
        subscription = self.ctx.socket(zmq.SUB)
        subscription.setsockopt(zmq.SUBSCRIBE, filter)
        subscription.setsockopt(zmq.LINGER, self.linger)

        subscription.connect(str(socket_id))

        self.subscriptions[str(socket_id)] = subscription

    def _destroy_socket(self, socket_id: SocketStruct):
        socket = self.subscriptions.get(str(socket_id))
        if socket is not None:
            socket.close()

            del self.subscriptions[str(socket_id)]

    def remove_subscription(self, socket_id: SocketStruct):
        if self.running:
            self.to_remove.append(socket_id)
        else:
            self._destroy_socket(socket_id)

    async def serve(self):
        self.running = True

        while self.running:
            await asyncio.sleep(0)

            for address, socket in self.subscriptions.items():
                try:
                    event = await socket.poll(timeout=self.timeout, flags=zmq.POLLIN)
                    if event:
                        msg = await socket.recv()

                        # Allow subclassing of a hook to verify or process a message before putting it in the queue
                        handled_msg = self.handle_msg(msg)
                        if handled_msg is not None:
                            self.received.append((handled_msg, address))
                except zmq.error.ZMQError as e:
                    socket.close()

                    socket = self.ctx.socket(zmq.SUB)
                    socket.setsockopt(zmq.SUBSCRIBE, b'')
                    socket.setsockopt(zmq.LINGER, self.linger)

                    socket.connect(str(address))

            # Destory sockets async
            for address in self.to_remove:
                self._destroy_socket(address)
            self.to_remove = []

    def handle_msg(self, msg):
        return msg

    def stop(self):
        self.running = False