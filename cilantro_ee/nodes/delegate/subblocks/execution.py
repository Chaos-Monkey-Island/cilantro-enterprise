from cilantro_ee.messages import capnp as schemas
from cilantro_ee.storage.state import MetaDataStorage
from contracting.db.cr.client import SubBlockClient
from contracting.stdlib.bridge.time import Datetime

from decimal import Decimal
from datetime import datetime
import os
import capnp

transaction_capnp = capnp.load(os.path.dirname(schemas.__file__) + '/transaction.capnp')


class Metadata:
    def __init__(self, proof, signature, timestamp):
        self.proof = proof
        self.signature = signature
        self.timestamp = timestamp


class Payload:
    def __init__(self, sender, nonce, processor, stamps_supplied, contract_name, function_name, kwargs):
        self.sender = sender
        self.nonce = nonce
        self.processor = processor
        self.stampsSupplied = stamps_supplied
        self.contractName = contract_name
        self.functionName = function_name
        self.kwargs = kwargs


class UnpackedContractTransaction:
    def __init__(self, capnp_struct: transaction_capnp.Transaction):
        self.metadata = Metadata(proof=capnp_struct.metadata.proof,
                                 signature=capnp_struct.metadata.signature,
                                 timestamp=capnp_struct.metadata.timestamp)

        kwargs = {}
        for entry in capnp_struct.payload.kwargs.entries:
            if entry.value.which() == 'fixedPoint':
                kwargs[entry.key] = Decimal(entry.value.fixedPoint)
            else:
                kwargs[entry.key] = getattr(entry.value, entry.value.which())

        self.payload = Payload(sender=capnp_struct.payload.sender,
                               nonce=capnp_struct.payload.nonce,
                               processor=capnp_struct.payload.processor,
                               stamps_supplied=capnp_struct.payload.stampsSupplied,
                               contract_name=capnp_struct.payload.contractName,
                               function_name=capnp_struct.payload.functionName,
                               kwargs=kwargs)


class TransactionExecutor:
    def __init__(self, sbb_idx, num_sbb, loop):
        self.client = SubBlockClient(sbb_idx=sbb_idx, num_sbb=num_sbb, loop=loop)
        self.pending_transactions = []
        self.state = MetaDataStorage()

    def execute_subblock(self, input_hash, tx_batch, timestamp, sb_idx):
        callback = self.create_sb_contender

        # Pass protocol level variables into environment so they are accessible at runtime in smart contracts
        block_hash = self.state.latest_block_hash
        block_num = self.state.latest_block_num

        dt = datetime.utcfromtimestamp(timestamp)
        dt_object = Datetime(year=dt.year,
                             month=dt.month,
                             day=dt.day,
                             hour=dt.hour,
                             minute=dt.minute,
                             second=dt.second,
                             microsecond=dt.microsecond)

        environment = {
            'block_hash': block_hash,
            'block_num': block_num,
            'now': dt_object
        }

        transactions = []
        for transaction in tx_batch:
            transactions.append(UnpackedContractTransaction(transaction))
            self.pending_transactions.append(transaction)

        result = self.client.execute_sb(input_hash,
                                        transactions,
                                        sb_idx,
                                        callback,
                                        environment=environment)

        self.log.success('RESULT FOR TX BATCH: {}'.format(result))

        if result:
            self._next_block_to_make.state = NextBlockState.PROCESSED
            return True

        return False

