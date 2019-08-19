from cilantro_ee.messages import capnp as schemas

from enum import Enum, unique
import hashlib
import os
import capnp

transaction_capnp = capnp.load(os.path.dirname(schemas.__file__) + '/transaction.capnp')

@unique
class NextBlockState(Enum):
    NOT_READY = 0
    READY = 1
    PROCESSED = 2


# raghu
class SBClientManager:
    def __init__(self, sbb_idx, loop):
        # self.client = SubBlockClient(sbb_idx=sbb_idx, num_sbb=NUM_SB_PER_BLOCK, loop=loop)
        self.next_sm_index = 0
        self.max_caches = 2
        self.sb_caches = []


class NextBlockToMake:
    def __init__(self, block_index: int=0, state: NextBlockState=NextBlockState.READY):
        self.next_block_index = block_index
        self.state = state


class WorkQueue:
    def __init__(self, parent):
        self.pending_transactions = []
        self.finalized_transactions = []
        self.timestamp = None
        self.nonce = 0
        self.parent = parent

    def empty_input_hash(self):
        self.nonce += 1

        h = hashlib.sha3_256()
        h.update(self.parent)
        h.update(str(self.nonce))

        return h.digest()

# This is a convenience struct to hold all data related to a sub-block in one place.
# Since we have more than one sub-block per process, SBB'er will hold an array of SubBlockManager objects
class WorkManager:
    def __init__(self, masters=[]):
        # Masters is a list, map it to each subblock tx queue thingy

        self.processors = {master: WorkQueue(parent=master) for master in masters}
        self.current_subblock_index = 0
        self.last_execution = None

    def increment_current_subblock_index(self):
        pass

    def make_next_subblock(self):
        pass

    def add_transaction_batch(self, transaction_batch: transaction_capnp.TransactionBatch):
        # Add it to the correct PendingSubBlock based on the processors mapping
        # Drops batches that are not for its own workers
        queue = self.processors.get(transaction_batch.sender)
        if queue is not None:
            queue.pending_transactions.append(transaction_batch)