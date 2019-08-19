from cilantro_ee.protocol import services
from cilantro_ee.storage.state import MetaDataStorage
from cilantro_ee.storage.vkbook import PhoneBook
from cilantro_ee.constants.ports import MN_PUB_PORT
from contracting.db.cr.client import SubBlockClient
from cilantro_ee.messages.message import MessageTypes
from cilantro_ee.messages import capnp as schemas
from cilantro_ee.protocol.wallet import _verify
from cilantro_ee.protocol.transaction import transaction_is_valid

import hashlib
import time
import json
import asyncio
import zmq.asyncio
import os
import capnp

transaction_capnp = capnp.load(os.path.dirname(schemas.__file__) + '/transaction.capnp')

CORES = 4


# Convenience method until Overlay server and client, LSocket, and all that crap are gone
async def resolve_vk(vk: str, ctx: zmq.Context, port: 9999):
    find_message = ['find', vk]
    find_message = json.dumps(find_message).encode()

    node_ip = await services.reqrep.get(services.core.sockstr('tcp://127.0.0.1:10002'),
                                        msg=find_message,
                                        ctx=ctx,
                                        timeout=3000)

    d = json.loads(node_ip)
    ip = d.get(vk)
    s = None

    if ip is not None:
        # Got the ip! Check if it is a tcp string or just an IP. This should be fixed later
        if services.core.SocketStruct.is_valid(ip):
            s = services.core.sockstr(ip)
            s.port = port
        else:
            # Just an IP...
            s = services.core.SocketStruct(services.core.Protocols.TCP, id=ip, port=port)

    return s


class SubBlockBuilder:
    def __init__(self,
                 idx: int,
                 total_builders: int,
                 loop: asyncio.AbstractEventLoop,
                 global_masters=PhoneBook.masternodes):

        self.state = MetaDataStorage()

        self.ctx = zmq.asyncio.Context()

        self.idx = idx
        self.total_builders = total_builders

        # Byte representation of process
        # Max of 256 builders. Enough?
        self.identity = bytes([idx])

        self.client = SubBlockClient(sbb_idx=idx, num_sbb=self.total_builders, loop=loop)

        self.block_manager_ipc_mailbox = services.async.Mailbox(ctx=self.ctx)
        self.transaction_batch_subscription = services.pubsub.SubscriptionService(ctx=self.ctx)

        # Create Sub sockets
        self.master_vks = global_masters[self.idx::CORES]

    async def connect_to_vks(self, vks):
        # Resolve the IPs for the VKs this SBB has to connect to
        resolves = [resolve_vk(vk=vk,
                               ctx=self.ctx,
                               port=MN_PUB_PORT) for vk in vks]

        # Await the entire group of them asynchronously
        sockets = await asyncio.gather(*resolves)

        # Add each socket to the subscription service
        for socket in sockets:
            self.transaction_batch_subscription.add_subscription(socket, filter=b'tx')

    async def process_transaction_batch_subscription_messages(self):
        # Pull from the subscription message queue
        while True:
            if len(self.transaction_batch_subscription.received) > 0:
                transactions = self.transaction_batch_subscription.received.pop(0)

                # Do shit with transactions
                msg_filter, msg_type, msg_blob = transactions

                if msg_type == MessageTypes.TRANSACTION_BATCH:

                    batch = transaction_capnp.TransactionBatch.from_bytes_packed(msg_blob)

                    batch_is_valid = self.validate_transaction_batch(batch)

                    if batch_is_valid:
                        pass

    def validate_transaction_batch(self, transaction_batch: transaction_capnp.TransactionBatch):
        if transaction_capnp.sender not in self.master_vks:
            return False

        if len(transaction_batch.transactions) < 1:
            self.log.info('Empty bag. Tossing.')
            return False

        timestamp = transaction_batch.timestamp
        self.log.info(timestamp, time.time())

        if timestamp <= self.sb_managers[index].processed_txs_timestamp:
            self.log.debug(
                "Got timestamp {} that is prior to the most recent timestamp {} for sb_manager {} tho"
                    .format(timestamp, self.sb_managers[index].processed_txs_timestamp, index))
            return False

        # Set up a hasher for input hash and a list for valid txs
        h = hashlib.sha3_256()
        valid_transactions = []

        for tx in transaction_batch.transactions:
            # Double check to make sure all transactions are valid
            if transaction_is_valid(tx=tx,
                                    expected_processor=transaction_batch.sender,
                                    driver=self.state,
                                    strict=False):
                valid_transactions.append(tx)

            # Hash all transactions regardless because the proof from masternodes is derived from all hashes
            h.update(tx.as_builder().to_bytes_packed())

        input_hash = h.digest()

        if not _verify(transaction_batch.sender, input_hash, transaction_batch.signature):
            return False

    async def process_block_manager_ipc_messages(self):
        while True:
            if len(self.block_manager_ipc_mailbox.inbox) > 0:
                _id, message = self.block_manager_ipc_mailbox.inbox.pop(0)
                msg_type, msg_blob = message

                if msg_type == MessageTypes.MAKE_NEXT_BLOCK:
                    self.log.success("MAKE NEXT BLOCK SIGNAL")
                    self._make_next_sub_block()
                    return

                elif msg_type == MessageTypes.ALIGN_INPUT_HASH:
                    msg = subblock_capnp.AlignInputHash.from_bytes_packed(msg_blob)
                    self.align_input_hashes(msg)

                elif msg_type == MessageTypes.FAIL_BLOCK_NOTIFICATION:
                    self._fail_block(msg)

    def increment_work_bag(self):
        pass

    def decrement_work_bag(self):
        pass