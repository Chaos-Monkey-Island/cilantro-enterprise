import asyncio

import zmq

from cilantro_ee.protocol.services.core import SocketStruct, Protocols
from cilantro_ee.protocol.wallet import Wallet


class Mailbox:
    def __init__(self,
                 inbound_address: SocketStruct,
                 outbound_address: SocketStruct,
                 wallet: Wallet,
                 ctx: zmq.Context,
                 linger=2000,
                 poll_timeout=2000):

        if inbound_address.protocol == Protocols.TCP:
            inbound_address.id = '*'

        self.inbound_address = inbound_address.zmq_url()
        self.outbound_address = outbound_address.zmq_url()

        self.wallet = wallet
        self.ctx = ctx

        self.inbox_socket = None

        self.linger = linger
        self.poll_timeout = poll_timeout

        self.running = False

        self.inbox = []
        self.outbox = []

    async def serve(self):
        self.setup_socket()

        self.running = True

        while self.running:
            try:
                event = await self.inbox_socket.poll(timeout=self.poll_timeout, flags=zmq.POLLIN)
                if event:
                    _id = await self.inbox_socket.recv()
                    msg = await self.inbox_socket.recv()
                    asyncio.ensure_future(self.inbox.append([_id, msg]))

            except zmq.error.ZMQError:
                self.inbox_socket.close()
                self.setup_socket()

        self.inbox_socket.close()

    def setup_socket(self):
        self.inbox_socket = self.ctx.socket(zmq.ROUTER)
        self.inbox_socket.setsockopt(zmq.LINGER, self.linger)
        self.inbox_socket.bind(self.inbound_address)

    async def deliver_messages(self):
        while True:
            if len(self.outbox) > 0:
                message = self.outbox.pop(0)

                socket = self.ctx.socket(zmq.REQ)
                socket.setsockopt(zmq.LINGER, self.linger)
                s


class AsyncInbox:
    def __init__(self, socket_id: SocketStruct, wallet: Wallet, ctx: zmq.Context, linger=2000, poll_timeout=2000):
        socket_id.id = '*'

        self.address = str(socket_id)

        self.wallet = wallet
        self.ctx = ctx

        self.socket = None

        self.linger = linger
        self.poll_timeout = poll_timeout

        self.running = False

        self.mailbox = []

    async def serve(self):
        self.setup_socket()

        self.running = True

        while self.running:
            try:
                event = await self.socket.poll(timeout=self.poll_timeout, flags=zmq.POLLIN)
                if event:
                    _id = await self.socket.recv()
                    msg = await self.socket.recv()
                    asyncio.ensure_future(self.handle_msg(_id, msg))

            except zmq.error.ZMQError:
                self.socket.close()
                self.setup_socket()

        self.socket.close()

    async def handle_msg(self, _id, msg):
        await self.return_msg(_id, msg)

    async def return_msg(self, _id, msg):
        sent = False
        while not sent:
            try:
                await self.socket.send_multipart([_id, msg])
                sent = True
            except zmq.error.ZMQError:
                self.socket.close()
                self.setup_socket()

    def setup_socket(self):
        self.socket = self.ctx.socket(zmq.ROUTER)
        self.socket.setsockopt(zmq.LINGER, self.linger)
        self.socket.bind(self.address)

    def stop(self):
        self.running = False


class AsyncOutbox:
    def __init__(self, socket_id: SocketStruct, wallet: Wallet, ctx: zmq.Context, linger=2000, poll_timeout=2000):
        self.ctx = ctx
        self.wallet = wallet
        self.address = str(socket_id)

        self.linger = linger
        self.poll_timeout = poll_timeout

        self.socket = self.ctx.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.LINGER, self.linger)

    def send(self, _id, msg_type, msg_payload):
        pass