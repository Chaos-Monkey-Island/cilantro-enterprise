from cilantro_ee.storage.state import MetaDataStorage
from cilantro_ee.storage.vkbook import PhoneBook
from cilantro_ee.constants.ports import MN_PUB_PORT
from contracting.db.cr.client import SubBlockClient
from cilantro_ee.protocol.comm import services
import json
import asyncio
import zmq.asyncio

CORES = 4

# Convenience method until Overlay server and client, LSocket, and all that crap are gone
async def resolve_vk(vk: str, ctx: zmq.Context, port: 9999):
    find_message = ['find', vk]
    find_message = json.dumps(find_message).encode()

    node_ip = await services.get(services._socket('tcp://127.0.0.1:10002'),
                 msg=find_message,
                 ctx=ctx,
                 timeout=3000)

    d = json.loads(node_ip)
    ip = d.get(vk)
    s = None

    if ip is not None:
        # Got the ip! Check if it is a tcp string or just an IP. This should be fixed later
        if services.SocketStruct.is_valid(ip):
            s = services._socket(ip)
            s.port = port
        else:
            # Just an IP...
            s = services.SocketStruct(services.Protocols.TCP, id=ip, port=port)

    return s


class SubBlockBuilder:
    def __init__(self,
                 comm_socket: services.SocketStruct,
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

        # Listen to messages from the Block Manager through an IPC Dealer socket
        # self.ipc_dealer = self.ctx.socket(zmq.DEALER)
        # self.ipc_dealer.setsockopt(zmq.IDENTITY, self.identity)
        # self.ipc_dealer.connect(comm_socket.zmq_url())

        self.transaction_batch_subscription = services.SubscriptionService(self.ctx)

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
                msg = self.transaction_batch_subscription.received.pop(0)

                msg_filter, msg_type, msg_blob = msg
                if msg_type == MessageTypes.TRANSACTION_BATCH and 0 <= index < len(self.sb_managers):

                    batch = transaction_capnp.TransactionBatch.from_bytes_packed(msg_blob)

                    if len(batch.transactions) < 1:
                        self.log.info('Empty bag. Tossing.')
                        continue

                    self.log.info('Got tx batch with {} txs for sbb {}'.format(len(batch.transactions), index))

                    if batch.sender.hex() not in PhoneBook.masternodes:
                        self.log.critical('RECEIVED TX BATCH FROM NON DELEGATE')
                        return

                    else:
                        self.log.success('{} is a masternode!'.format(batch.sender.hex()))

                    timestamp = batch.timestamp
                    self.log.info(timestamp, time.time())

                    if timestamp <= self.sb_managers[index].processed_txs_timestamp:
                        self.log.debug(
                            "Got timestamp {} that is prior to the most recent timestamp {} for sb_manager {} tho"
                            .format(timestamp, self.sb_managers[index].processed_txs_timestamp, index))
                        return

                    # Set up a hasher for input hash and a list for valid txs
                    h = hashlib.sha3_256()
                    valid_transactions = []

                    for tx in batch.transactions:
                        # Double check to make sure all transactions are valid
                        if transaction_is_valid(tx=tx,
                                                expected_processor=batch.sender,
                                                driver=self.state,
                                                strict=False):

                            valid_transactions.append(tx)

                        # Hash all transactions regardless because the proof from masternodes is derived from all hashes
                        h.update(tx.as_builder().to_bytes_packed())

                    input_hash = h.digest()

                    if not _verify(batch.sender, input_hash, batch.signature):
                        return
