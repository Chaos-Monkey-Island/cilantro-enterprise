import unittest
from unittest import TestCase
from cilantro.logger import get_logger
from tests.contracts.smart_contract_testcase import *
from seneca.execute_sc import execute_contract
import seneca.smart_contract_user_libs.stdlib as std
import time

log = get_logger("TestElection")

class TestCurrency(SmartContractTestCase):
    @contract('currency')
    def test_get_balance(self, currency):
        balance = currency.get_balance('DAVIS')
        self.assertEqual(balance, 3696947)

    @contract('currency')
    def test_get_balance_failed(self, currency):
        with self.assertRaises(IndexError) as context:
            currency.get_balance('MumboJumbo')

    @contract('currency')
    def test_wallet_exists(self, currency):
        self.assertTrue(currency.wallet_exists('DAVIS'))

    @contract('currency')
    def test_wallet_exists_failed(self, currency):
        self.assertFalse(currency.wallet_exists('MumboJumbo'))

    @contract('currency')
    def test_create_wallet(self, currency):
        currency.create_wallet('MumboJumbo')
        self.assertTrue(currency.wallet_exists('MumboJumbo'))

    @contract('currency')
    def test_create_wallet_failed(self, currency):
        with self.assertRaises(Exception) as context:
            currency.create_wallet('DAVIS')

    @contract(
        ('DAVIS', 'currency'),
        ('FALCON', 'currency')
    )
    def test_transfer_coins(self, davis, falcon):
        davis.transfer_coins('FALCON', 47)
        self.assertEqual(davis.get_balance('DAVIS'), 3696900)
        self.assertEqual(davis.get_balance('FALCON'), 47)

    @contract(('DAVIS', 'currency'))
    def test_transfer_coins_not_enough_funds(self, davis):
        with self.assertRaises(Exception) as context:
            davis.transfer_coins('FALCON', 3696950)

    @contract(('DAVIS', 'currency'))
    def test_transfer_coins_negative(self, davis):
        with self.assertRaises(Exception) as context:
            davis.transfer_coins('FALCON', -123)

    @contract(('DAVIS', 'currency'))
    def test_approve(self, davis):
        davis.approve('FALCON', 123)
        self.assertEqual(davis.get_approved('DAVIS', 'FALCON'), 123)

    @contract(('DAVIS', 'currency'))
    def test_approve_transfer(self, davis):
        davis.approve('FALCON', 123)
        davis.transfer_coins_from('DAVIS', 'FALCON', 100)
        self.assertEqual(davis.get_approved('DAVIS', 'FALCON'), 23)
        self.assertEqual(davis.get_balance('DAVIS'), 3696847)
        self.assertEqual(davis.get_balance('FALCON'), 100)

    @contract(('DAVIS', 'currency'))
    def test_approve_transfer_not_approved(self, davis):
        with self.assertRaises(Exception) as context:
            davis.transfer_coins_from('DAVIS', 'FALCON', 1)

    @contract(('DAVIS', 'currency'))
    def test_approve_transfer_not_enough_approval(self, davis):
        davis.approve('FALCON', 123)
        with self.assertRaises(Exception) as context:
            davis.transfer_coins_from('DAVIS', 'FALCON', 10000)

    @contract(('DAVIS','currency'))
    def test_lock_coins(self, davis):
        davis.lock_coins(500, std.timedelta(seconds=3))
        davis.is_locked('DAVIS')
        self.assertEqual(davis.get_balance('DAVIS'), 3696447)

    @contract(('DAVIS','currency'))
    def test_lock_coins_not_enough(self, davis):
        with self.assertRaises(Exception) as context:
            davis.lock_coins(3696950, std.timedelta(seconds=1))


    @contract(('DAVIS','currency'))
    def test_unlock_coins(self, davis):
        davis.lock_coins(500, std.timedelta(seconds=1))
        self.assertEqual(davis.get_balance('DAVIS'), 3696447)
        self.assertTrue(davis.is_locked('DAVIS'))
        time.sleep(1.5)
        davis.unlock_coins()
        self.assertEqual(davis.get_balance('DAVIS'), 3696947)
        self.assertFalse(davis.is_locked('DAVIS'))

    @contract(('DAVIS','currency'))
    def test_unlock_coins(self, davis):
        davis.lock_coins(500, std.timedelta(seconds=1))
        self.assertEqual(davis.get_balance('DAVIS'), 3696447)
        with self.assertRaises(Exception) as context:
            davis.unlock_coins()

    @contract(('DAVIS','currency'))
    def test_unlock_coins_fail(self, davis):
        with self.assertRaises(Exception) as context:
            davis.unlock_coins()

    @contract(('DAVIS','currency'))
    def test_lock_coins_negative(self, davis):
        with self.assertRaises(Exception) as context:
            davis.lock_coins(-123, std.timedelta(seconds=1))

if __name__ == '__main__':
    unittest.main()