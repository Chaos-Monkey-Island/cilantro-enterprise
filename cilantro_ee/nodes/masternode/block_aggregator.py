from cilantro_ee.core.sockets.services import SubscriptionService, SocketStruct, Protocols
from cilantro_ee.nodes.masternode.block_contender import BlockContender
from cilantro_ee.core.messages.message import Message

from cilantro_ee.core.utils.block_sub_block_mapper import BlockSubBlockMapper


import time
import asyncio


class BNKind:
    NEW = 0
    SKIP = 1
    FAIL = 2


class Block:
    def __init__(self, min_quorum, max_quorum, current_quorum,
                 subblocks_per_block, builders_per_block, contacts):

        self.contender = BlockContender(subblocks_per_block, builders_per_block, contacts=contacts)
        self.started = False
        self.current_quorum = current_quorum
        self.min_quorum = min_quorum
        self.max_quorum = max_quorum

    def consensus_is_reached(self):
        if self.contender.is_consensus_reached() or self.contender.get_current_quorum_reached() >= self.current_quorum:
            return True
        return False

    def can_adjust_quorum(self):
        current_block_quorum = self.contender.get_current_quorum_reached()
        return current_block_quorum >= self.min_quorum and current_block_quorum >= (9 * self.current_quorum // 10)


class BlockAggregator:
    def __init__(self, subscription: SubscriptionService,
                 block_timeout=60*1000,
                 current_quorum=0,
                 min_quorum=0,
                 max_quorum=1,
                 contacts=None):

        self.subblock_subscription_service = subscription

        self.block_timeout = block_timeout
        self.contacts = contacts

        self.current_quorum = current_quorum
        self.min_quorum = min_quorum
        self.max_quorum = max_quorum

        print(self.contacts.masternodes)

        self.block_sb_mapper = BlockSubBlockMapper(self.contacts.masternodes)

        self.pending_block = Block(min_quorum=self.min_quorum,
                                   max_quorum=self.max_quorum,
                                   current_quorum=self.current_quorum,
                                   subblocks_per_block=self.block_sb_mapper.num_sb_per_block,
                                   builders_per_block=self.block_sb_mapper.num_sb_builders,
                                   contacts=self.contacts)

        self.running = True

    async def gather_block(self):
        while not self.pending_block.started and len(self.subblock_subscription_service.received) == 0 and self.running:
            await asyncio.sleep(0)

        self.pending_block.started = True

        start_time = time.time()

        while time.time() - start_time < self.block_timeout:
            if len(self.subblock_subscription_service.received) > 0:
                # Pop the next SBC off of the subscription LIFO queue
                sbc, _ = self.subblock_subscription_service.received.pop(0)
                msg_type, msg, sender, timestamp, is_verified = Message.unpack_message_2(sbc)

                # Deserialize it and add it to the pending block
                self.pending_block.contender.add_sbc(sender, msg)

                if self.pending_block.consensus_is_reached():
                    block = self.pending_block.contender.get_sb_data()
                    if self.pending_block.contender.is_empty():
                        # SKIP!
                        self.setup_new_block_contender()
                        return block, BNKind.SKIP
                    else:
                        # REGULAR
                        self.setup_new_block_contender()
                        return block, BNKind.NEW

                elif not self.pending_block.contender.is_consensus_possible():
                    # FAIL?
                    block = self.pending_block.contender.get_sb_data()
                    self.setup_new_block_contender()
                    return block, BNKind.FAIL

        # This will be hit if timeout is reached
        block = self.pending_block.contender.get_sb_data()
        # Check if we can adjust the quorum and return
        if self.pending_block.can_adjust_quorum():
            self.pending_block.current_quorum = self.pending_block.contender.get_current_quorum_reached()
            # REGULAR!
            self.setup_new_block_contender()
            return block, BNKind.NEW
        # Otherwise, fail the block
        else:
            # FAIL!
            self.setup_new_block_contender()
            return block, BNKind.FAIL

    def setup_new_block_contender(self):
        self.pending_block.started = False
        self.pending_block = Block(min_quorum=self.min_quorum,
                                   max_quorum=self.max_quorum,
                                   current_quorum=self.current_quorum,
                                   subblocks_per_block=self.block_sb_mapper.num_sb_per_block,
                                   builders_per_block=self.block_sb_mapper.num_sb_builders,
                                   contacts=self.contacts)
