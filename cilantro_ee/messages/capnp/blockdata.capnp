@0xda0328d77fef6562;

using SB = import "subblock.capnp";


struct BlockMetaData {
    blockHash @0 :Data;
    merkleRoots @1 :List(Data);
    inputHashes @2 :List(Data);
    prevBlockHash @3 :Data;
    timestamp @4 :UInt64;
    blockOwners @5 :List(Text);
    blockNum @6 :UInt32;
}


struct BlockData {
    blockHash @0 :Data;
    blockNum @1 :UInt32;
    blockOwners @2 :List(Data);
    prevBlockHash @3 :Data;
    subBlocks @4 :List(SB.SubBlock);
}

struct BlockIndexRequest {
    blockHash @0: Data;
    sender @1: Data;
}

struct StateUpdateRequest {
    blockHash @0 :Data;
}


struct StateUpdateReply {
    blockData @0 :BlockData;
}

struct BlockDataRequest {
    blockNum @0: UInt32;
}

struct LatestBlockHeightRequest {
    timestamp @0 :UInt64;
}

struct LatestBlockHashRequest {
    timestamp @0 :UInt64;
}

struct LatestBlockHeightReply {
    blockHeight @0: UInt32;
}

struct LatestBlockHashRequest {
    blockHash @0: Data;
}

struct BadRequest {
    timestamp @0: UInt64;
}