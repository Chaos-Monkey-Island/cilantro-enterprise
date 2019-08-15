import zmq

from cilantro_ee.protocol.services.core import SocketStruct
from cilantro_ee.protocol.wallet import Wallet


class RequestReplyService:
    def __init__(self, socket_id: SocketStruct, wallet: Wallet, ctx: zmq.Context, linger=2000, poll_timeout=2000):
        self.address = str(socket_id)
        self.wallet = wallet
        self.ctx = ctx

        self.socket = None

        self.linger = linger
        self.poll_timeout = poll_timeout

        self.running = False

    async def serve(self):
        self.socket = self.ctx.socket(zmq.REP)
        self.socket.setsockopt(zmq.LINGER, self.linger)
        self.socket.bind(self.address)

        self.running = True

        while self.running:
            try:
                event = await self.socket.poll(timeout=self.poll_timeout, flags=zmq.POLLIN)
                if event:
                    msg = await self.socket.recv()
                    result = self.handle_msg(msg)

                    if result is None:
                        result = b''

                    await self.socket.poll(timeout=self.poll_timeout, flags=zmq.POLLOUT)
                    await self.socket.send(result)

            except zmq.error.ZMQError as e:
                self.socket = self.ctx.socket(zmq.REP)
                self.socket.setsockopt(zmq.LINGER, self.linger)
                self.socket.bind(self.address)

        self.socket.close()

    def handle_msg(self, msg):
        return msg

    def stop(self):
        self.running = False


async def get(socket_id: SocketStruct, msg: bytes, ctx:zmq.Context, timeout=500, linger=2000, retries=10):
    if retries <= 0:
        return None

    socket = ctx.socket(zmq.REQ)
    socket.setsockopt(zmq.LINGER, linger)
    try:
        # Allow passing an existing socket to save time on initializing a _new one and waiting for connection.
        socket.connect(str(socket_id))

        await socket.send(msg)

        event = await socket.poll(timeout=timeout, flags=zmq.POLLIN)
        if event:
            response = await socket.recv()

            socket.close()

            return response
        else:
            socket.close()
            return None
    except Exception as e:
        socket.close()
        return await get(socket_id, msg, ctx, timeout, linger, retries-1)