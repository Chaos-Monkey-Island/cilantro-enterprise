from enum import Enum, unique

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


# This is a convenience struct to hold all data related to a sub-block in one place.
# Since we have more than one sub-block per process, SBB'er will hold an array of SubBlockManager objects
class SubBlockManager:
    def __init__(self, sub_block_index: int, sub_socket, processed_txs_timestamp: int=0):
        self.sub_block_index = sub_block_index
        self.connected_vk = None
        self.empty_input_iter = 0
        self.sub_socket = sub_socket
        self.processed_txs_timestamp = processed_txs_timestamp
        self.pending_txs = LinkedHashTable()
        self.to_finalize_txs = LinkedHashTable()

    def get_empty_input_hash(self):
        self.empty_input_iter += 1
        return Hasher.hash(self.connected_vk + str(self.empty_input_iter))