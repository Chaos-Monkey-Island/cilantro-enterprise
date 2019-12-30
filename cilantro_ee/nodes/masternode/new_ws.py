from sanic import Sanic
from sanic import response
from cilantro_ee.core.logger import get_logger
from sanic_cors import CORS
import json as _json
from contracting.client import ContractingClient

from cilantro_ee.core.messages.capnp_impl.capnp_impl import pack
from cilantro_ee.services.storage.master import MasterStorage
from cilantro_ee.services.storage.state import MetaDataStorage
from cilantro_ee.core.nonces import NonceManager

from cilantro_ee.core.messages.message_type import MessageType
from cilantro_ee.core.messages.message import Message

import ast
import ssl
import hashlib

log = get_logger("MN-WebServer")


class WebServer:
    def __init__(self, wallet, queue=[], port=8080, ssl_port=443, ssl_enabled=False,
                 ssl_cert_file='~/.ssh/server.csr',
                 ssl_key_file='~/.ssh/server.key',
                 workers=2, debug=False, access_log=False, max_queue_len=10_000):

        # Setup base Sanic class and CORS
        self.app = Sanic(__name__)
        self.app.config.update({
            'REQUEST_MAX_SIZE': 10000,
            'REQUEST_TIMEOUT': 5
        })
        self.cors = CORS(self.app, automatic_options=True)

        # Initialize the backend data interfaces
        self.client = ContractingClient()
        self.metadata_driver = MetaDataStorage()
        self.nonce_manager = NonceManager()

        self.static_headers = {}

        self.wallet = wallet
        self.queue = queue
        self.max_queue_len = max_queue_len

        self.port = port

        self.ssl_port = ssl_port
        self.ssl_enabled = ssl_enabled
        self.context = None

        # Create the SSL Context if needed
        if self.ssl_enabled:
            self.context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
            self.context.load_cert_chain(ssl_cert_file, keyfile=ssl_key_file)

        # Store other Sanic constants for when server starts
        self.workers = workers
        self.debug = debug
        self.access_log = access_log

    def start(self):
        # Transaction Routes
        self.app.add_route(self.submit_transaction, '/', methods=['POST', 'OPTIONS'])
        self.app.add_route(self.ping, '/ping', methods=['GET', 'OPTIONS'])
        self.app.add_route(self.get_id, '/id', methods=['GET'])
        self.app.add_route(self.get_nonce, '/nonce/<vk>', methods=['GET'])

        # State Routes
        self.app.add_route(self.get_methods, '/contracts/<contract>/methods', methods=['GET'])
        self.app.add_route(self.get_variable, '/contracts/<contract>/<variable>')
        self.app.add_route(self.get_contracts, '/contracts', methods=['GET'])
        self.app.add_route(self.get_contract, '/contracts/<contract>', methods=['GET'])

        # Block Explorer / Blockchain Routes
        self.app.add_route(self.get_latest_block, '/latest_block', methods=['GET', 'OPTIONS', ])
        self.app.add_route(self.get_block, '/blocks', methods=['GET', 'OPTIONS', ])

        # Start server with SSL enabled or not
        if self.ssl_enabled:
            self.app.run(host='127.0.0.1', port=self.ssl_port, workers=self.workers, debug=self.debug,
                         access_log=self.access_log, ssl=self.context)
        else:
            self.app.run(host='127.0.0.1', port=self.port, workers=self.workers, debug=self.debug,
                         access_log=self.access_log)

    # Main Endpoint to Submit TXs
    async def submit_transaction(self, request):
        if len(self.queue) > self.max_queue_len:
            return response.json({'error': "Queue full. Resubmit shortly."}, status=503)

        # Try to deserialize transaction.
        try:
            tx_bytes = request.body
            tx = Message.unpack_message(pack(int(MessageType.TRANSACTION)), tx_bytes)

        except Exception as e:
            return response.json({'error': 'Malformed transaction.'.format(e)}, status=400)

        # Put it in the rate limiter queue.
        self.queue.append(tx)

        h = hashlib.sha3_256()
        h.update(tx_bytes)
        tx_hash = h.digest()

        return response.json({'success': 'Transaction successfully submitted to the network.',
                              'hash': tx_hash.hex()})

    # Network Status
    async def ping(self, request):
        return response.json({'status': 'online'})

    # Get VK of this Masternode for Nonces
    async def get_id(self, request):
        return response.json({'verifying_key': self.wallet.verifying_key().hex()})

    # Get the Nonce of a VK
    async def get_nonce(self, request, vk):
        # Might have to change this sucker from hex to bytes.
        pending_nonce = self.nonce_manager.get_pending_nonce(processor=self.wallet.verifying_key(), sender=bytes.fromhex(vk))

        log.info('Pending nonce: {}'.format(pending_nonce))

        if pending_nonce is None:
            nonce = self.nonce_manager.get_nonce(processor=self.wallet.verifying_key(), sender=bytes.fromhex(vk))
            log.info('Pending nonce was none so got nonce which is {}'.format(nonce))
            if nonce is None:
                pending_nonce = 0
                log.info('Nonce was now so pending nonce is now zero.')
            else:
                pending_nonce = nonce
                log.info('Nonce was not none so setting pending nonce to it.')

        return response.json({'nonce': pending_nonce, 'processor': self.wallet.verifying_key().hex(), 'sender': vk})

    # Get all Contracts in State (list of names)
    async def get_contracts(self, request):
        contracts = self.client.get_contracts()
        return response.json({'contracts': contracts})

    # Get the source code of a specific contract
    async def get_contract(self, request, contract):
        contract_code = self.client.raw_driver.get_contract(contract)

        if contract_code is None:
            return response.json({'error': '{} does not exist'.format(contract)}, status=404)
        return response.json({'name': contract, 'code': contract_code}, status=200)

    async def get_methods(self, request, contract):
        contract_code = self.client.raw_driver.get_contract(contract)

        if contract_code is None:
            return response.json({'error': '{} does not exist'.format(contract)}, status=404)

        tree = ast.parse(contract_code)

        function_defs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]

        funcs = []
        for definition in function_defs:
            func_name = definition.name
            kwargs = [arg.arg for arg in definition.args.args]

            funcs.append({'name': func_name, 'arguments': kwargs})

        return response.json({'methods': funcs}, status=200)

    async def get_variable(self, request, contract, variable):
        contract_code = self.client.raw_driver.get_contract(contract)

        if contract_code is None:
            return response.json({'error': '{} does not exist'.format(contract)}, status=404)

        key = request.args.get('key')

        k = self.client.raw_driver.make_key(key=contract, field=variable, args=key)
        response = self.client.raw_driver.get(k)

        if response is None:
            return response.json({'value': None}, status=404)
        else:
            return response.json({'value': response}, status=200)

    async def get_latest_block(self, request):
        index = MasterStorage.get_last_n(1)
        latest_block_hash = index.get('blockHash')
        return response.json({'hash': '{}'.format(latest_block_hash)})

    async def get_block(self, request):
        if 'number' in request.json:
            num = request.json['number']
            block = MasterStorage.get_block(num)
            if block is None:
                return response.json({'error': 'Block at number {} does not exist.'.format(num)}, status=400)
        else:
            _hash = request.json['hash']
            block = MasterStorage.get_block(_hash)
            if block is None:
                return response.json({'error': 'Block with hash {} does not exist.'.format(_hash)}, status=400)

        return response.json(_json.dumps(block))
