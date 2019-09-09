class MessageTypes:
    MAKE_NEXT_BLOCK = b'\x00'
    PENDING_TRANSACTIONS = b'\x01'
    NO_TRANSACTIONS = b'\x02'
    READY_INTERNAL = b'\x05'
    READY_EXTERNAL = b'\x06'
    UPDATED_STATE_SYNC = b'\x07'

    TRANSACTION_DATA = b'\x08'
    MERKLE_PROOF = b'\x09'
    SUBBLOCK_CONTENDER = b'\x0a'
    BLOCK_INDEX_REQUEST = b'\x0b'
    BLOCK_INDEX_REPLY = b'\x0d'
    BLOCK_DATA_REQUEST = b'\x0e'
    BLOCK_DATA_REPLY = b'\x0f'
    BLOCK_NOTIFICATION = b'\x11'
    ALIGN_INPUT_HASH = b'\x12'
    BURN_INPUT_HASHES = b'\x13'

    TRANSACTION_BATCH = b'\x15'

    # update signals
    TRIGGER_UPDATE = b'\x16'
    UPDATE_READY = b'\x17'
    TRIGGER_SWITCH = b'\x18'
