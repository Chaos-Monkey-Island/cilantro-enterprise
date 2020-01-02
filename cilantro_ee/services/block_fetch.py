from cilantro_ee.core.sockets.socket_book import SocketBook
from cilantro_ee.services.storage.vkbook import VKBook
from cilantro_ee.core.top import TopBlockManager
from cilantro_ee.services.storage.state import MetaDataStorage
from cilantro_ee.core.crypto.wallet import Wallet
from cilantro_ee.core.messages.message import Message, MessageType
from cilantro_ee.core.canonical import verify_block
from cilantro_ee.core.sockets.services import get, defer
from cilantro_ee.services.storage.master import CilantroStorageDriver
from cilantro_ee.core.networking.parameters import ServiceType, NetworkParameters
import zmq.asyncio
import asyncio
from collections import Counter
import time


class ConfirmationCounter(Counter):
    def top_item(self):
        if len(self.most_common()[0]) > 0:
            return self.most_common()[0][0]
        return None

    def top_count(self):
        if len(self.most_common()) == 0:
            return 0
        return self.most_common()[0][1]


# Open a socket and to listen for new block notifications
class BlockFetcher:
    def __init__(self, wallet: Wallet,
                 ctx: zmq.asyncio.Context,
                 contacts: VKBook,
                 blocks: CilantroStorageDriver=None,
                 network_parameters=NetworkParameters(),
                 top=TopBlockManager(),
                 state=MetaDataStorage(),
                 masternode_sockets=None):

        self.contacts = contacts
        self.network_parameters = network_parameters
        self.masternodes = masternode_sockets or \
                           SocketBook("tcp://127.0.0.1",
                                      ServiceType.BLOCK_SERVER, ctx, self.network_parameters,
                                      self.contacts.contract.get_masternodes)
        self.top = top
        self.wallet = wallet
        self.ctx = ctx
        self.blocks = blocks
        self.state = state

        self.blocks_to_process = []

        self.in_catchup = False

    # Change to max received
    async def find_missing_block_indexes(self, confirmations=3, timeout=3000):
        await self.masternodes.refresh()
        responses = ConfirmationCounter()

        # In a 2 MN setup, a MN can only as one other MN
        confirmations = min(confirmations, len(self.masternodes.sockets.values()) - 1)

        futures = []
        # Fire off requests to masternodes on the network
        for master in self.masternodes.sockets.values():
            f = asyncio.ensure_future(self.get_latest_block_height(master))
            futures.append(f)

        # Iterate through the status of the
        now = time.time()
        while responses.top_count() < confirmations or time.time() - now > timeout:
            await defer()
            for f in futures:
                if f.done():
                    responses.update([f.result()])

                    # Remove future
                    futures.remove(f)

        return responses.top_item()

    async def get_latest_block_height(self, socket):
        request = Message.get_signed_message_packed_2(wallet=self.wallet,
                                                      msg_type=MessageType.LATEST_BLOCK_HEIGHT_REQUEST,
                                                      timestamp=int(time.time()))

        response = await get(socket_id=socket, msg=request, ctx=self.ctx, timeout=3000, retries=0, dealer=True)

        if response is not None:
            _, unpacked, _, _, _ = Message.unpack_message_2(response)

            return unpacked.blockHeight

    async def get_block_from_master(self, i: int, socket):
        request = Message.get_signed_message_packed_2(wallet=self.wallet,
                                                      msg_type=MessageType.BLOCK_DATA_REQUEST,
                                                      blockNum=i)

        response = await get(socket_id=socket, msg=request, ctx=self.ctx, timeout=3000, retries=0, dealer=True)

        if response is not None:
            msg_type, unpacked, _, _, _ = Message.unpack_message_2(response)

            if msg_type == MessageType.BLOCK_DATA:
                return unpacked

    async def find_valid_block(self, i, latest_hash, timeout=3000):
        await self.masternodes.refresh()

        block_found = False
        block = None

        futures = []
        # Fire off requests to masternodes on the network
        for master in self.masternodes.sockets.values():
            f = asyncio.ensure_future(self.get_block_from_master(i, master))
            futures.append(f)

        # Iterate through the status of the
        now = time.time()
        while not block_found or time.time() - now > timeout:
            await defer()
            for f in futures:
                if f.done():
                    block = f.result()
                    block_found = verify_block(subblocks=block.subBlocks,
                                               previous_hash=latest_hash,
                                               proposed_hash=block.blockHash)
                    futures.remove(f)

        return block

    async def fetch_blocks(self, latest_block_available=0):
        latest_block_stored = self.top.get_latest_block_number()
        latest_hash = self.top.get_latest_block_hash()

        if latest_block_available <= latest_block_stored:
            return

        for i in range(latest_block_stored, latest_block_available + 1):
            await self.find_and_store_block(i, latest_hash)
            latest_hash = self.top.get_latest_block_hash()

    async def find_and_store_block(self, block_num, block_hash):
        block = await self.find_valid_block(block_num, block_hash)

        if block is not None:
            block_dict = {
                'blockHash': block.blockHash,
                'blockNum': block_num,
                'blockOwners': [m for m in block.blockOwners],
                'prevBlockHash': block_hash,
                'subBlocks': [s for s in block.subBlocks]
            }

            # Only store if master, update state if master or delegate

            if self.blocks is not None:
                self.blocks.put(block_dict)

            self.state.update_with_block(block_dict)
            self.top.set_latest_block_hash(block.blockHash)
            self.top.set_latest_block_number(block_num)

    # Main Catchup function. Called at launch of node
    async def sync(self):
        self.in_catchup = True

        current_height = await self.find_missing_block_indexes()
        latest_block_stored = self.top.get_latest_block_number()

        while current_height < latest_block_stored:

            await self.fetch_blocks(current_height)
            current_height = await self.find_missing_block_indexes()

        self.in_catchup = False

        # Finds all of the blocks that were processed while syncing
        while len(self.blocks_to_process) > 0:
            b = self.blocks_to_process.pop(0)
            await self.find_and_store_block(b.blockNum, b.blockHash)

    # Secondary Catchup function. Called if a new block is created.
    async def intermediate_sync(self, block):
        if self.in_catchup:
            self.blocks_to_process.append(block)
        else:
            # store block directly
            await self.find_and_store_block(block.blockNum, block.blockHash)

    # Catchup for masternodes who already have storage and state is corrupted for some reason
    async def sync_blocks_with_state(self):
        if self.blocks is None:
            return

        last_block = self.blocks.get_last_n(1, CilantroStorageDriver.INDEX)[0]
        last_stored_block_num = last_block.get('blockNum')
        last_state_block_num = self.top.get_latest_block_number()

        while last_state_block_num < last_stored_block_num:
            last_state_block_num += 1
            block_dict = self.blocks.get_block(last_state_block_num)

            self.state.update_with_block(block_dict)

    async def is_caught_up(self):
        current_height = await self.find_missing_block_indexes()
        latest_block_stored = self.top.get_latest_block_number()
        return current_height >= latest_block_stored

# struct BlockData {
#     blockHash @0 :Data;
#     blockNum @1 :UInt32;
#     blockOwners @2 :List(Data);
#     prevBlockHash @3 :Data;
#     subBlocks @4 :List(SB.SubBlock);
# }
