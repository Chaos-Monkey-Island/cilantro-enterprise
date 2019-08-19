import cilantro_ee.protocol.services.async
import cilantro_ee.protocol.services.core
import zmq.asyncio
from cilantro_ee.protocol.wallet import Wallet
from unittest import TestCase
import asyncio


async def stop_server(s, timeout):
    await asyncio.sleep(timeout)
    s.stop()


class TestAsyncServer(TestCase):
    def setUp(self):
        self.ctx = zmq.asyncio.Context()

    def tearDown(self):
        self.ctx.destroy()

    def test_init(self):
        w = Wallet()
        cilantro_ee.protocol.services.async.AsyncInbox(cilantro_ee.protocol.services.core.sockstr('tcp://127.0.0.1:10000'), w, self.ctx)

    def test_addresses_correct(self):
        w = Wallet()
        m = cilantro_ee.protocol.services.async.AsyncInbox(cilantro_ee.protocol.services.core.sockstr('tcp://127.0.0.1:10000'), w, self.ctx)

        self.assertEqual(m.address, 'tcp://*:10000')

    def test_sockets_are_initially_none(self):
        w = Wallet()
        m = cilantro_ee.protocol.services.async.AsyncInbox(cilantro_ee.protocol.services.core.sockstr('tcp://127.0.0.1:10000'), w, self.ctx)

        self.assertIsNone(m.socket)

    def test_setup_frontend_creates_socket(self):
        w = Wallet()
        m = cilantro_ee.protocol.services.async.AsyncInbox(cilantro_ee.protocol.services.core.sockstr('tcp://127.0.0.1:10000'), w, self.ctx)
        m.setup_socket()

        self.assertEqual(m.socket.type, zmq.ROUTER)
        self.assertEqual(m.socket.getsockopt(zmq.LINGER), m.linger)

    def test_sending_message_returns_it(self):
        w = Wallet()
        m = cilantro_ee.protocol.services.async.AsyncInbox(cilantro_ee.protocol.services.core.sockstr('tcp://127.0.0.1:10000'), w, self.ctx, linger=500, poll_timeout=500)

        async def get(msg):
            socket = self.ctx.socket(zmq.DEALER)
            socket.connect('tcp://127.0.0.1:10000')

            await socket.send(msg)

            res = await socket.recv()

            return res

        tasks = asyncio.gather(
            m.serve(),
            get(b'howdy'),
            stop_server(m, 0.2),
        )

        loop = asyncio.get_event_loop()
        res = loop.run_until_complete(tasks)

        self.assertEqual(res[1], b'howdy')
