from cilantro_ee.protocol.comm.services import AsyncInbox, SocketStruct, Protocols
from cilantro_ee.messages import capnp as schemas
from cilantro_ee.core.top import TopBlockManager
from cilantro_ee.core.messages.message import Message
from cilantro_ee.core.messages.message_type import MessageType
import os
import capnp
import struct

import blockdata_capnp
subblock_capnp = capnp.load(os.path.dirname(schemas.__file__) + '/subblock.capnp')

# Provide a block driver to enable data and index requests
# Otherwise, this will just return latest num and hash, which both delegates and masters can do
class BlockServer(AsyncInbox):
    def __init__(self, socket_id, wallet, ctx, linger, poll_timeout, driver=None, top=TopBlockManager()):
        self.driver = driver
        self.top = top
        super().__init__(socket_id=socket_id,
                         wallet=wallet,
                         ctx=ctx,
                         linger=linger,
                         poll_timeout=poll_timeout)

    async def handle_msg(self, _id, msg):
        msg_type = msg[0]
        msg_blob = msg[1:]

        msg_type, msg, sender, timestamp, is_verified = Message.unpack_message(msg_type=struct.pack('B', msg_type),
                                                                               message=msg_blob)

        if msg_type == MessageType.BLOCK_DATA_REQUEST and self.driver is not None:
            block_dict = await self.driver.get_block(msg.blockNum)

            await self.return_msg(_id, block_dict.get('blob'))

        elif msg_type == MessageType.BLOCK_INDEX_REQUEST and self.driver is not None:
            block_dict = await self.driver.get_block(msg.blockNum)

            await self.return_msg(_id, block_dict.get('blob'))

        elif msg_type == MessageType.LATEST_BLOCK_HEIGHT_REQUEST:
            reply = Message.get_signed_message_packed(signee=self.wallet.sk.encode(),
                                                      msg_type=MessageType.LATEST_BLOCK_HEIGHT_REPLY,
                                                      blockHeight=self.top.get_latest_block_number())
            await self.return_msg(_id, reply)

        elif msg_type == MessageType.LATEST_BLOCK_HASH_REQUEST:
            reply = Message.get_signed_message_packed(signee=self.wallet.sk.encode(),
                                                      msg_type=MessageType.LATEST_BLOCK_HASH_REPLY,
                                                      blockHash=self.top.get_latest_block_hash())
            await self.return_msg(_id, reply)

        else:
            await self.return_msg(_id, b'bad')
