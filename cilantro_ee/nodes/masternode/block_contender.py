from cilantro_ee.sockets.services import AsyncInbox
from collections import defaultdict
from cilantro_ee.storage import BlockchainDriver

import capnp
import os

from cilantro_ee.core import canonical
from cilantro_ee.messages import Message, MessageType, schemas
from cilantro_ee.crypto.wallet import _verify
from cilantro_ee.containers.merkle_tree import merklize

import asyncio
import time
from copy import deepcopy
import math

from cilantro_ee.logger.base import get_logger

subblock_capnp = capnp.load(os.path.dirname(schemas.__file__) + '/subblock.capnp')


class SBCException(Exception):
    pass


class SBCBadMessage(SBCException):
    pass


class SBCInvalidSignatureError(SBCException):
    pass


class SBCBlockHashMismatchError(SBCException):
    pass


class SBCMerkleLeafVerificationError(SBCException):
    pass


class SBCIndexMismatchError(SBCException):
    pass


class SBCIndexGreaterThanPossibleError(SBCException):
    pass


class SBCInbox(AsyncInbox):
    def __init__(self, driver: BlockchainDriver, expected_subblocks=4, *args, **kwargs):
        self.q = []
        self.driver = driver
        self.expected_subblocks = expected_subblocks
        self.log = get_logger('SBC')
        super().__init__(*args, **kwargs)

    async def handle_msg(self, _id, msg):
        msg_type, msg_blob, _, _, _ = Message.unpack_message_2(msg)

        # Ignore bad message types
        if msg_type != MessageType.SUBBLOCK_CONTENDERS:
            return

        if len(msg_blob.contenders) != self.expected_subblocks:
            return

        # Make sure all the contenders are valid
        all_valid = True
        for i in range(len(msg_blob.contenders)):
            try:
                self.sbc_is_valid(msg_blob.contenders[i], i)
            except SBCException as e:
                self.log.error(type(e))
                all_valid = False

        # Add the whole contender
        if all_valid:
            self.q.append(msg_blob.contenders)
            self.log.info('Added new SBC')

    def sbc_is_valid(self, sbc, sb_idx=0):
        if sbc.subBlockNum != sb_idx:
            raise SBCIndexMismatchError

        # Make sure signer is in the delegates
        if len(sbc.transactions) == 0:
            msg = sbc.inputHash
        else:
            msg = sbc.merkleTree.leaves[0]

        valid_sig = _verify(
            vk=sbc.signer,
            msg=msg,
            signature=sbc.merkleTree.signature
        )

        if not valid_sig:
            raise SBCInvalidSignatureError

        if sbc.prevBlockHash != self.driver.latest_block_hash:
            self.log.info(sbc.prevBlockHash)
            self.log.info(self.driver.latest_block_hash)
            raise SBCBlockHashMismatchError

        # idk
        if len(sbc.merkleTree.leaves) > 0:
            txs = [tx.as_builder().to_bytes_packed() for tx in sbc.transactions]
            expected_tree = merklize(txs)

            for i in range(len(expected_tree)):
                if expected_tree[i] != sbc.merkleTree.leaves[i]:
                    raise SBCMerkleLeafVerificationError

    def has_sbc(self):
        return len(self.q) > 0

    async def receive_sbc(self):
        while len(self.q) <= 0:
            await asyncio.sleep(0)

        return self.q.pop(0)


class CurrentContenders:
    def __init__(self, total_contacts=2, quorum_ratio=0.66, expected_subblocks=4):
        self.total_contacts = total_contacts
        self.consensus = math.ceil(total_contacts * quorum_ratio)

        self.sbcs = defaultdict(lambda: defaultdict(set))
        self.signatures = defaultdict(lambda: defaultdict(set))

        # Number of votes for most popular SBC. Used for consensus failure checking
        self.top_votes = defaultdict(int)

        # Finished SBCs
        self.finished = {}

        # Number of different input hashes we expect to recieve
        self.expected = expected_subblocks

        self.votes_left = defaultdict(lambda: total_contacts)

        self.log = get_logger('CON')

    # Should be dict. push Capnp away from protocol as much as possible
    def add_sbcs(self, sbcs):
        for sbc in sbcs:
            self.votes_left[sbc.inputHash] -= 1
            result_hash = sbc.merkleTree.leaves[0]

            self.sbcs[sbc.inputHash][result_hash].add(sbc)
            self.signatures[sbc.inputHash][result_hash].add((sbc.merkleTree.signature, sbc.signer))

            # If its done, put it in the list
            if len(self.sbcs[sbc.inputHash][result_hash]) >= self.consensus:
                self.finished[sbc.subBlockNum] = self.subblock_for_sbc_and_sigs(
                    sbcs=self.sbcs[sbc.inputHash][result_hash],
                    signatures=self.signatures[sbc.inputHash][result_hash]
                )

            # Update the top vote for this hash
            self.top_votes[sbc.inputHash] = max(self.top_votes[sbc.inputHash], len(self.sbcs[sbc.inputHash][result_hash]))

            # Check if consensus possible
            if self.votes_left[sbc.inputHash] + self.top_votes[sbc.inputHash] < self.consensus:
                self.finished[sbc.subBlockNum] = None

    def subblock_for_sbc_and_sigs(self, sbcs, signatures):
        sbc = sbcs.pop()
        sbcs.add(sbc)

        subblock = {
            'inputHash': sbc.inputHash,
            'transactions': [tx.to_dict() for tx in sbc.transactions],
            'merkleLeaves': [leaf for leaf in sbc.merkleTree.leaves],
            'subBlockNum': sbc.subBlockNum,
            'prevBlockHash': sbc.prevBlockHash,
            'signatures': []
        }

        for sig in signatures:
            subblock['signatures'].append({
                'signer': sig[0],
                'signature': sig[1]
            })

        return subblock


def now_in_ms():
    return int(time.time() * 1000)


class Aggregator:
    def __init__(self, socket_id, ctx, driver, expected_subblocks=4):
        self.expected_subblocks = expected_subblocks
        self.sbc_inbox = SBCInbox(
            socket_id=socket_id,
            ctx=ctx,
            driver=driver,
            expected_subblocks=self.expected_subblocks
        )
        self.driver = driver
        self.log = get_logger('AGG')

    async def gather_subblocks(self, total_contacts, quorum_ratio=0.66, expected_subblocks=4, timeout=1000):
        self.sbc_inbox.expected_subblocks = expected_subblocks

        contenders = CurrentContenders(total_contacts, quorum_ratio=quorum_ratio, expected_subblocks=expected_subblocks)

        while len(contenders.finished) < expected_subblocks:
            if self.sbc_inbox.has_sbc():
                sbcs = await self.sbc_inbox.receive_sbc() # Can probably make this raw sync code
                contenders.add_sbcs(sbcs)
            await asyncio.sleep(0)

        for i in range(expected_subblocks):
            if contenders.finished.get(i) is None:
                contenders.finished[i] = None

        self.log.info('Done aggregating new block.')
        self.log.info(self.driver.latest_block_num)

        subblocks = deepcopy(contenders.finished)
        del contenders

        return canonical.block_from_subblocks(
            [v for _, v in sorted(subblocks.items())],
            previous_hash=self.driver.latest_block_hash,
            block_num=self.driver.latest_block_num + 1
        )

    async def start(self):
        asyncio.ensure_future(self.sbc_inbox.serve())

    def stop(self):
        self.sbc_inbox.stop()

    # def build_subblocks_from_contenders(self, contender):
    #     subblock = {
    #         'inputHash'
    #     }
    #     pass

# struct SubBlockContender {
#     inputHash @0 :Data;
#     transactions @1: List(T.TransactionData);
#     merkleTree @2 :MerkleTree;
#     signer @3 :Data;
#     subBlockNum @4: UInt8;
#     prevBlockHash @5: Data;
# }