import os
import capnp
from cilantro_ee.messages.capnp_impl import capnp_struct as schemas
import bson
import hashlib
from cilantro_ee.containers.merkle_tree import merklize
from cilantro_ee.messages import Message, MessageType

subblock_capnp = capnp.load(os.path.dirname(schemas.__file__) + '/subblock.capnp')
block_capnp = capnp.load(os.path.dirname(schemas.__file__) + '/blockdata.capnp')

GENESIS_HASH = b'\x00' * 32


def format_dictionary(d: dict) -> dict:
    for k, v in d.items():
        assert type(k) == str, 'Non-string key types not allowed.'
        if type(v) == list:
            for i in range(len(v)):
                if isinstance(v[i], dict):
                    v[i] = format_dictionary(v[i])
        elif isinstance(v, dict):
            d[k] = format_dictionary(v)
    return {k: v for k, v in sorted(d.items())}


def block_from_subblocks(subblocks, previous_hash: bytes, block_num: int) -> dict:
    block_hasher = hashlib.sha3_256()
    block_hasher.update(previous_hash)

    deserialized_subblocks = []

    for subblock in subblocks:
        if subblock is None:
            return get_failed_block(previous_hash=previous_hash, block_num=block_num)

        if type(subblock) != dict:
            subblock = subblock.to_dict()

        sb = format_dictionary(subblock)
        deserialized_subblocks.append(sb)

        encoded_sb = bson.BSON.encode(sb)
        block_hasher.update(encoded_sb)

    block = {
        'blockHash': block_hasher.digest(),
        'blockNum': block_num,
        'prevBlockHash': previous_hash,
        'subBlocks': deserialized_subblocks
    }

    return block


def verify_block(subblocks, previous_hash: bytes, proposed_hash: bytes):
    # Verify signatures!
    block_hasher = hashlib.sha3_256()
    block_hasher.update(previous_hash)

    deserialized_subblocks = []

    for subblock in subblocks:
        sb = subblock.to_dict()

        sb = format_dictionary(sb)
        deserialized_subblocks.append(sb)

        encoded_sb = bson.BSON.encode(sb)
        block_hasher.update(encoded_sb)

    if block_hasher.digest() == proposed_hash:
        return True

    return False


def block_is_skip_block(block: dict):
    if len(block['subBlocks']) == 0:
        return False

    for subblock in block['subBlocks']:
        if len(subblock['transactions']):
            return False

    return True


def get_failed_block(previous_hash: bytes, block_num: int) -> dict:
    block = {
        'blockHash': b'\x00' * 32,
        'blockNum': block_num,
        'prevBlockHash': previous_hash,
        'subBlocks': []
    }
    return block


def get_genesis_block():
    block = {
        'blockHash': b'\x00' * 32,
        'blockNum': 1,
        'prevBlockHash': b'\x00' * 32,
        'subBlocks': []
    }
    return block


def block_is_genesis(block):
    return block == get_genesis_block()


def block_is_failed(block, previous_hash: bytes, block_num: int):
    return block == get_failed_block(previous_hash, block_num)


def message_blob_to_dict_block(block):
    pass


def capnp_to_dict_block(block):
    return block_capnp.BlockData.to_dict(block)


def dict_to_capnp_block(block):
    return block_capnp.BlockData.from_dict(block)


def dict_to_msg_block(block):
    return Message.get_message_packed_2(MessageType.BLOCK_DATA, **block)


def build_sbc_from_work_results(results, wallet, previous_block_hash, input_hash, sb_num=0):
    if len(results) > 0:
        merkle = merklize([r.to_bytes_packed() for r in results])
        proof = wallet.sign(merkle[0])
    else:
        merkle = merklize([input_hash])
        proof = wallet.sign(input_hash)

    merkle_tree = subblock_capnp.MerkleTree.new_message(
        leaves=[leaf for leaf in merkle],
        signature=proof
    )

    sbc = subblock_capnp.SubBlockContender.new_message(
        inputHash=input_hash,
        transactions=[r for r in results],
        merkleTree=merkle_tree,
        signer=wallet.verifying_key(),
        subBlockNum=sb_num,
        prevBlockHash=previous_block_hash
    )

    return sbc

