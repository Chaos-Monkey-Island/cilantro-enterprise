from unittest import TestCase
import secrets
import os
import capnp
from tests import random_txs

from cilantro_ee.messages import capnp as schemas
from cilantro_ee.core.nonces import NonceManager, PENDING_NONCE_KEY, NONCE_KEY

import blockdata_capnp
subblock_capnp = capnp.load(os.path.dirname(schemas.__file__) + '/subblock.capnp')
transaction_capnp = capnp.load(os.path.dirname(schemas.__file__) + '/transaction.capnp')
signal_capnp = capnp.load(os.path.dirname(schemas.__file__) + '/signals.capnp')


class TestNonceManager(TestCase):
    def setUp(self):
        self.r = NonceManager()
        self.r.driver.flush()

    def tearDown(self):
        self.r.driver.flush()

    def test_update_nonce_empty_hash_adds_anything(self):
        sender = b'123'
        processor = b'456'
        tx_payload = transaction_capnp.TransactionPayload.new_message(
            sender=sender,
            processor=processor,
            nonce=999,
        )

        nonces = {}
        self.r.update_nonce_hash(nonces, tx_payload)

        self.assertEqual(nonces.get((b'456', b'123')), 1000)

    def test_update_nonce_when_new_max_nonce_found(self):
        nonces = {}

        sender = b'123'
        processor = b'456'
        tx_payload = transaction_capnp.TransactionPayload.new_message(
            sender=sender,
            processor=processor,
            nonce=999,
        )

        self.r.update_nonce_hash(nonces, tx_payload)

        sender = b'123'
        processor = b'456'
        tx_payload = transaction_capnp.TransactionPayload.new_message(
            sender=sender,
            processor=processor,
            nonce=1000,
        )

        self.r.update_nonce_hash(nonces, tx_payload)

        self.assertEqual(nonces.get((b'456', b'123')), 1001)

    def test_update_nonce_only_keeps_max_values(self):
        nonces = {}

        sender = b'123'
        processor = b'456'
        tx_payload = transaction_capnp.TransactionPayload.new_message(
            sender=sender,
            processor=processor,
            nonce=1000,
        )

        self.r.update_nonce_hash(nonces, tx_payload)

        sender = b'123'
        processor = b'456'
        tx_payload = transaction_capnp.TransactionPayload.new_message(
            sender=sender,
            processor=processor,
            nonce=999,
        )

        self.r.update_nonce_hash(nonces, tx_payload)

        self.assertEqual(nonces.get((b'456', b'123')), 1001)

    def test_update_nonce_keeps_multiple_nonces(self):
        nonces = {}

        sender = b'123'
        processor = b'456'
        tx_payload = transaction_capnp.TransactionPayload.new_message(
            sender=sender,
            processor=processor,
            nonce=1000,
        )

        self.r.update_nonce_hash(nonces, tx_payload)

        sender = b'124'
        processor = b'456'
        tx_payload = transaction_capnp.TransactionPayload.new_message(
            sender=sender,
            processor=processor,
            nonce=999,
        )

        self.r.update_nonce_hash(nonces, tx_payload)

        self.assertEqual(nonces.get((b'456', b'123')), 1001)
        self.assertEqual(nonces.get((b'456', b'124')), 1000)

    def test_nonces_are_set_and_deleted_from_commit_nonces(self):
        n1 = (secrets.token_bytes(32), secrets.token_bytes(32))
        n2 = (secrets.token_bytes(32), secrets.token_bytes(32))
        n3 = (secrets.token_bytes(32), secrets.token_bytes(32))
        n4 = (secrets.token_bytes(32), secrets.token_bytes(32))
        n5 = (secrets.token_bytes(32), secrets.token_bytes(32))
        n6 = (secrets.token_bytes(32), secrets.token_bytes(32))

        nonces = {
            n1: 5,
            n3: 3,
            n5: 6,
            n6: 100
        }

        self.r.set_pending_nonce(n1[0], n1[1], 5)
        self.r.set_pending_nonce(n2[0], n2[1], 999)
        self.r.set_pending_nonce(n3[0], n3[1], 3)
        self.r.set_pending_nonce(n4[0], n4[1], 888)
        self.r.set_pending_nonce(n5[0], n5[1], 6)

        self.r.set_nonce(n1[0], n1[1], 4)
        self.r.set_nonce(n3[0], n3[1], 2)
        self.r.set_nonce(n5[0], n5[1], 5)

        self.assertEqual(len(self.r.driver.iter(PENDING_NONCE_KEY)), 5)
        self.assertEqual(len(self.r.driver.iter(NONCE_KEY)), 3)

        self.r.commit_nonces(nonce_hash=nonces)

        self.assertEqual(len(self.r.driver.iter(PENDING_NONCE_KEY)), 2)
        self.assertEqual(len(self.r.driver.iter(NONCE_KEY)), 4)

    def test_delete_pending_nonce_removes_all_pending_nonce_but_not_normal_nonces(self):
        self.r.set_pending_nonce(processor=secrets.token_bytes(32),
                                 sender=secrets.token_bytes(32),
                                 nonce=100)

        self.r.set_pending_nonce(processor=secrets.token_bytes(32),
                                 sender=secrets.token_bytes(32),
                                 nonce=100)

        self.r.set_pending_nonce(processor=secrets.token_bytes(32),
                                 sender=secrets.token_bytes(32),
                                 nonce=100)

        self.r.set_pending_nonce(processor=secrets.token_bytes(32),
                                 sender=secrets.token_bytes(32),
                                 nonce=100)

        self.r.set_pending_nonce(processor=secrets.token_bytes(32),
                                 sender=secrets.token_bytes(32),
                                 nonce=100)

        self.r.set_nonce(processor=secrets.token_bytes(32),
                         sender=secrets.token_bytes(32),
                         nonce=100)

        self.assertEqual(len(self.r.driver.iter(PENDING_NONCE_KEY)), 5)
        self.assertEqual(len(self.r.driver.iter(NONCE_KEY)), 1)

        self.r.delete_pending_nonces()

        self.assertEqual(len(self.r.driver.iter(PENDING_NONCE_KEY)), 0)
        self.assertEqual(len(self.r.driver.iter(NONCE_KEY)), 1)

    def test_commit_nonce_when_nonce_hash_is_none_that_it_commits_all_current_pending_nonces(self):
        n1 = (secrets.token_bytes(32), secrets.token_bytes(32))
        n2 = (secrets.token_bytes(32), secrets.token_bytes(32))
        n3 = (secrets.token_bytes(32), secrets.token_bytes(32))
        n4 = (secrets.token_bytes(32), secrets.token_bytes(32))
        n5 = (secrets.token_bytes(32), secrets.token_bytes(32))
        n6 = (secrets.token_bytes(32), secrets.token_bytes(32))

        self.r.set_pending_nonce(processor=n1[0], sender=n1[1], nonce=100)
        self.r.set_pending_nonce(processor=n2[0], sender=n2[1], nonce=100)
        self.r.set_pending_nonce(processor=n3[0], sender=n3[1], nonce=100)
        self.r.set_pending_nonce(processor=n4[0], sender=n4[1], nonce=100)
        self.r.set_pending_nonce(processor=n5[0], sender=n5[1], nonce=100)

        self.r.set_nonce(processor=n6[0], sender=n6[1], nonce=100)

        self.assertEqual(len(self.r.driver.iter(PENDING_NONCE_KEY)), 5)
        self.assertEqual(len(self.r.driver.iter(NONCE_KEY)), 1)

        self.r.commit_nonces()

        self.assertEqual(len(self.r.driver.iter(PENDING_NONCE_KEY)), 0)
        self.assertEqual(len(self.r.driver.iter(NONCE_KEY)), 6)

        self.assertEqual(self.r.get_nonce(processor=n1[0], sender=n1[1]), 100)
        self.assertEqual(self.r.get_nonce(processor=n2[0], sender=n2[1]), 100)
        self.assertEqual(self.r.get_nonce(processor=n3[0], sender=n3[1]), 100)
        self.assertEqual(self.r.get_nonce(processor=n4[0], sender=n4[1]), 100)
        self.assertEqual(self.r.get_nonce(processor=n5[0], sender=n5[1]), 100)

    def test_update_nonces_with_block(self):
        block = random_txs.random_block(txs=20)

        self.r.update_nonces_with_block(block)

        nonces = self.r.driver.iter(NONCE_KEY)

        self.assertEqual(len(nonces), 20)

        vals = []
        for n in nonces:
            vals.append(self.r.driver.get(n))

        self.assertEqual(sorted(vals), list(range(1, 21)))
