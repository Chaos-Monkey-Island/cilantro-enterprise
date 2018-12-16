# Base python imports
import argparse
import json
import time
from decimal import *

# Pip installed python imports

# Lamden imports
import cilantro.utils.test.god as god

def setup_argparse(parser):
    # Add positional arguments
    parser.add_argument('to', help='the destination vk for the transaction', type=str)

    # Add non-positional arguments with requirement forced
    parser.add_argument('-a', '--amount', help='amount of tau to send', type=Decimal, required=True)
    parser.add_argument('-s', '--sk', help='the secret key to send the transaction from', type=str, required=True)

    # Add non-positional arguments that are optional
    parser.add_argument('-n', '--nonce', help='the nonce for the transaction, optional if nonces are disabled for the network', type=str, default=None)
    parser.add_argument('--retrycount', help='Set the number of transaction retries', type=int, default=10)
    parser.add_argument('--backoff', help='Set the backoff factor on retries', type=float, default=1.2)
    parser.add_argument('--baseretry', help='Set the base retry timeout in seconds', type=int, default=5)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    setup_argparse(p)
    args = p.parse_args()

    # Read in static config
    with open('static-config.json') as df:
        static_config = json.load(df)
    mn_urls = [ 'http://{}:8080'.format(x) for x in static_config['mn-ips'] ]

    # Set static config in god module
    god.God.mn_urls = mn_urls
    god.God.multi_master = True
    
    # Generate and send tx
    currency_tx = god.God.create_currency_tx((args.sk,""), ("",args.to), args.amount, args.nonce)
    backoff_factor = args.backoff
    waittime = args.baseretry

    # Leverage underlying round robin functionality in God module
    for _ in range(args.retrycount):
        response = god.God.send_tx(currency_tx)
        if response and response.status_code == 200:
            break
        print("Waiting {} seconds before continuing".format(waittime))
        time.sleep(waittime)
        waittime *= backoff_factor

    if not response or response.status_code != 200:
        print("Error sending transaction after {} retries".format(args.retry_count))
    else:
        print(json.dumps(response.json(), indent=2))
