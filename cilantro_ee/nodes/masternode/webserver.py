from sanic import Sanic
from sanic.response import json, text
from cilantro_ee.logger.base import get_logger
from sanic_cors import CORS, cross_origin
import json as _json
from contracting.client import ContractingClient
from cilantro_ee.messages.transaction.contract import ContractTransaction
from cilantro_ee.messages.transaction.publish import PublishTransaction
from cilantro_ee.messages.transaction.container import TransactionContainer
from cilantro_ee.messages.transaction.ordering import OrderingContainer
from cilantro_ee.nodes.masternode.nonce import NonceManager

from cilantro_ee.constants import conf
from cilantro_ee.utils.hasher import Hasher

from multiprocessing import Queue
import ast
import ssl
import time

WEB_SERVER_PORT = 8080
SSL_WEB_SERVER_PORT = 443
NUM_WORKERS = 2

app = Sanic(__name__)

ssl_enabled = False
ssl_cert = '~/.ssh/server.csr'
ssl_key = '~/.ssh/server.key'

CORS(app, automatic_options=True)
log = get_logger("MN-WebServer")
client = ContractingClient()

static_headers = {}

#
# @app.middleware('response')
# async def set_secure_headers(request, response):
#     SecureHeaders.sanic(response)


def _respond_to_request(payload, headers={}, status=200, resptype='json'):
    if resptype == 'json':
        return json(payload, headers=dict(headers, **static_headers), status=status)
    elif resptype == 'text':
        return text(payload, headers=dict(headers, **static_headers), status=status)


# ping to check whether server is online or not
@app.route("/ping", methods=["GET","OPTIONS",])
async def ping(request):
    return _respond_to_request({'status':'online'})


@app.route("/", methods=["POST","OPTIONS",])
async def submit_transaction(request):
    if app.queue.full():
        return _respond_to_request({'error': "Queue full! Cannot process any more requests"}, status=503)

    try:
        tx_bytes = request.body
        container = TransactionContainer.from_bytes(tx_bytes)
        tx = container.open()  # Deserializing the tx automatically validates the signature and POW
    except Exception as e:
        return _respond_to_request({'error': 'Error opening transaction: {}'.format(e)}, status=400)

    # TODO do we need to do any other validation? tx size? check sufficient stamps?
    # TODO -- check that timestamp on tx meta is within reasonable bound

    # Check the transaction type and make sure we can handle it
    if type(tx) not in (ContractTransaction, PublishTransaction):
        return _respond_to_request({'error': 'Cannot process transaction of type {}'.format(type(tx))}, status=400)

    if conf.SSL_ENABLED:
        # Verify the nonce, and remove it from db if its valid so it cannot be used again
        # TODO do i need to make this 'check and delete' atomic? What if two procs request at the same time?
        if not NonceManager.check_if_exists(tx.nonce):
            return _respond_to_request({'error': 'Nonce {} has expired or was never created'.format(tx.nonce)}, status=400)
        log.spam("Removing nonce {}".format(tx.nonce))
        NonceManager.delete_nonce(tx.nonce)

    # TODO @faclon why do we need this if we check the queue at the start of this func? --davis
    ord_container = OrderingContainer.create(tx)
    try: app.queue.put_nowait(ord_container.serialize())
    except: return _respond_to_request({'error': "Queue full! Cannot process any more requests"}, status=503)

    # Return transaction hash and nonce to users (not sure which they will need) --davis
    return _respond_to_request({'success': 'Transaction successfully submitted to the network.',
                 'nonce': tx.nonce, 'hash': Hasher.hash(tx)})

# Returns {'contracts': JSON List of strings}
@app.route('/contracts', methods=['GET'])
async def get_contracts(request):
    contracts = client.get_contracts()
    return json({'contracts': contracts})


@app.route('/contracts/<contract>', methods=['GET'])
async def get_contract(request, contract):
    contract_code = client.raw_driver.get_contract(contract)

    if contract_code is None:
        return json({'error': '{} does not exist'.format(contract)}, status=404)
    return json({'name': contract, 'code': contract_code}, status=200)


@app.route("/contracts/<contract>/methods", methods=['GET'])
async def get_methods(request, contract):
    contract_code = client.raw_driver.get_contract(contract)

    if contract_code is None:
        return json({'error': '{} does not exist'.format(contract)}, status=404)

    tree = ast.parse(contract_code)

    function_defs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]

    funcs = []
    for definition in function_defs:
        func_name = definition.name
        kwargs = [arg.arg for arg in definition.args.args]

        funcs.append({'name': func_name, 'arguments': kwargs})

    return json({'methods': funcs}, status=200)


@app.route('/contracts/<contract>/<variable>')
async def get_variable(request, contract, variable):
    contract_code = client.raw_driver.get_contract(contract)

    if contract_code is None:
        return json({'error': '{} does not exist'.format(contract)}, status=404)

    key = request.args.get('key')

    if key is None:
        response = client.raw_driver.get('{}.{}'.format(contract, variable))
    else:
        response = client.raw_driver.get('{}.{}:{}'.format(contract, variable, key))

    if response is None:
        return json({'value': None}, status=404)
    else:
        return json({'value': response}, status=200)


# Expects json object such that:
'''
{
    'name': 'string',
    'code': 'string'
}
'''
@app.route('/lint', methods=['POST'])
async def lint_contract(request):
    code = request.json.get('code')

    if code is None:
        return json({'error': 'no code provided'}, status=500)

    violations = client.lint(request.json.get('code'))
    return json({'violations': violations}, status=200)


@app.route('/compile', methods=['POST'])
async def compile_contract(request):
    code = request.json.get('code')

    if code is None:
        return json({'error': 'no code provided'}, status=500)

    violations = client.lint(request.json.get('code'))

    if violations is None:
        compiled_code = client.compiler.parse_to_code(code)
        return json({'code': compiled_code}, status=200)

    return json({'violations': violations}, status=500)


@app.route('/submit', methods=['POST'])
async def submit_contract(request):
    code = request.json.get('code')
    name = request.json.get('name')

    if code is None or name is None:
        return json({'error': 'malformed payload'}, status=500)

    violations = client.lint(code)

    if violations is None:
        client.submit(code, name=name)

    else:
        return json({'violations': violations}, status=500)

    return json({'success': True}, status=200)


@app.route('/exists', methods=['GET'])
async def contract_exists(request):
    contract_code = client.get_contract(request.json.get('name'))

    if contract_code is None:
        return json({'exists': False}, status=404)
    else:
        return json({'exists': True}, status=200)


#blocks






def start_webserver(q):
    time.sleep(30)
    log.debugv("TESTING Creating REST server on port {}".format(WEB_SERVER_PORT))
    app.queue = q
    if ssl_enabled:
        context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(ssl_cert, keyfile=ssl_key)
        app.run(host='0.0.0.0', port=SSL_WEB_SERVER_PORT, workers=NUM_WORKERS, debug=False, access_log=False, ssl=context)
    else:
        app.run(host='0.0.0.0', port=WEB_SERVER_PORT, workers=NUM_WORKERS, debug=False, access_log=False)


if __name__ == '__main__':
    import pyximport; pyximport.install()
    if not app.config.REQUEST_MAX_SIZE:
        app.config.update({
            'REQUEST_MAX_SIZE': 5,
            'REQUEST_TIMEOUT': 5
        })
    start_webserver(Queue())
