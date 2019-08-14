from decimal import Decimal

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