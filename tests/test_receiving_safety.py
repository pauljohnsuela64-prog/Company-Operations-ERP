"""Receiving retry policy and pre-write validation without database connections."""
import unittest
from unittest.mock import patch
import uuid

import mysql.connector
import goods_receipt_repository as gr


class ReceivingSafetyTests(unittest.TestCase):
    def test_missing_or_invalid_tokens_never_open_connections(self):
        for token in (None, '', 'invalid'):
            with self.subTest(token=token), patch.object(gr, 'get_connection') as connect:
                with self.assertRaisesRegex(ValueError, 'submission identifier'):
                    gr.create_goods_receipt(1, 1, 1, {1:'1'}, submission_id=token)
                connect.assert_not_called()

    def test_invalid_items_never_open_connections(self):
        for items in (None, [], {1:'NaN'}, {1:'Infinity'}, {1:'-1'}, {1:'1.001'}, {1:'10000000000'}, {1:'1', '1':'1'}, {1.5:'1'}):
            with self.subTest(items=items), patch.object(gr, 'get_connection') as connect:
                with self.assertRaises(ValueError):
                    gr.create_goods_receipt(1, 1, 1, items, submission_id=str(uuid.uuid4()))
                connect.assert_not_called()

    def test_deadlock_and_lock_timeout_retry_same_normalized_delivery(self):
        for errno in (1205,1213):
            token=str(uuid.uuid4())
            expected=(42,'GR-000042','PARTIALLY_RECEIVED')
            with self.subTest(errno=errno), patch.object(gr, '_create_goods_receipt_transaction', side_effect=[mysql.connector.DatabaseError('lock conflict', errno=errno),expected]) as transaction:
                self.assertEqual(gr.create_goods_receipt(1,1,1,{'3':'1.25'},submission_id=token),expected)
                self.assertEqual(transaction.call_count,2)
                self.assertEqual(transaction.call_args_list[0],transaction.call_args_list[1])
                self.assertEqual(transaction.call_args.args[-1],token)

    def test_lock_retries_are_bounded(self):
        with patch.object(gr, '_create_goods_receipt_transaction', side_effect=mysql.connector.DatabaseError('deadlock', errno=1213)) as transaction:
            with self.assertRaisesRegex(ValueError,'same submission identifier'):
                gr.create_goods_receipt(1,1,1,{1:'1'},submission_id=str(uuid.uuid4()))
            self.assertEqual(transaction.call_count,3)

    def test_connection_loss_does_not_claim_receipt_was_not_saved(self):
        with patch.object(gr, '_create_goods_receipt_transaction', side_effect=mysql.connector.InterfaceError('connection lost',errno=2013)) as transaction:
            with self.assertRaisesRegex(ValueError,'check whether it was saved'):
                gr.create_goods_receipt(1,1,1,{1:'1'},submission_id=str(uuid.uuid4()))
            transaction.assert_called_once()

    def test_missing_migration_reports_clear_error(self):
        with patch.object(gr, '_create_goods_receipt_transaction', side_effect=mysql.connector.ProgrammingError('unknown column',errno=1054)):
            with self.assertRaisesRegex(ValueError,'migration'):
                gr.create_goods_receipt(1,1,1,{1:'1'},submission_id=str(uuid.uuid4()))


if __name__=='__main__':
    unittest.main()
