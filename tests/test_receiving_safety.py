"""Receiving retry policy and pre-write validation without database connections."""
import unittest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from itertools import cycle
import uuid

import mysql.connector
import goods_receipt_repository as gr


class ReceivingSafetyTests(unittest.TestCase):
    def test_lock_failure_is_retryable_only_after_confirmed_rollback(self):
        for errno in (1205, 1213):
            connection = MagicMock()
            connection.cursor.return_value.execute.side_effect = mysql.connector.DatabaseError('lock', errno=errno)
            with self.subTest(errno=errno), patch.object(gr, 'get_connection', return_value=connection):
                with self.assertRaises(gr._RetryableReceiptError):
                    gr._create_goods_receipt_transaction(1, 1, 1, {1: Decimal('1')}, None, str(uuid.uuid4()))
            connection.rollback.assert_called_once()
            connection.commit.assert_not_called()
            connection.close.assert_called_once()

    def test_cursor_creation_and_cleanup_failures_close_connection_without_retry(self):
        for creation in (True, False):
            connection = MagicMock()
            if creation:
                connection.cursor.side_effect = mysql.connector.DatabaseError('cursor', errno=1205)
            else:
                connection.cursor.return_value.execute.side_effect = mysql.connector.DatabaseError('lock', errno=1213)
                connection.cursor.return_value.close.side_effect = mysql.connector.DatabaseError('close', errno=1205)
            with self.subTest(creation=creation), patch.object(gr, 'get_connection', return_value=connection) as connect:
                if creation:
                    # Creation failed before any SQL; rollback confirms safe retry.
                    with self.assertRaises(ValueError):
                        gr.create_goods_receipt(1, 1, 1, {1: '1'}, submission_id=str(uuid.uuid4()))
                    self.assertEqual(connect.call_count, 3)
                else:
                    with self.assertRaises(ValueError):
                        gr.create_goods_receipt(1, 1, 1, {1: '1'}, submission_id=str(uuid.uuid4()))
                    connect.assert_called_once()
                self.assertEqual(connection.close.call_count, connect.call_count)

    def test_rollback_lock_error_never_automatically_replays(self):
        connection = MagicMock()
        connection.cursor.return_value.execute.side_effect = mysql.connector.DatabaseError('lock', errno=1213)
        connection.rollback.side_effect = mysql.connector.DatabaseError('rollback failed', errno=1205)
        with patch.object(gr, 'get_connection', return_value=connection) as connect:
            with self.assertRaisesRegex(ValueError, 'could not be confirmed'):
                gr.create_goods_receipt(1, 1, 1, {1: '1'}, submission_id=str(uuid.uuid4()))
        connect.assert_called_once()
        connection.close.assert_called_once()

    def test_commit_lock_error_never_automatically_replays(self):
        connection = MagicMock()
        connection.cursor.return_value.fetchone.side_effect = cycle([
            {'status': 'SENT', 'po_number': 'PO-1', 'request_id': None}, None, {'warehouse_id': 1},
            {'quantity': Decimal('0')}, {'remaining_items': 1},
        ])
        connection.cursor.return_value.fetchall.return_value = [
            {'purchase_order_item_id': 1, 'item_id': 1,
             'ordered_quantity': Decimal('2'), 'received_quantity': Decimal('0')},
        ]
        connection.cursor.return_value.lastrowid = 1
        connection.commit.side_effect = mysql.connector.DatabaseError('commit failed', errno=1213)
        with patch.object(gr, 'get_connection', return_value=connection) as connect:
            with self.assertRaisesRegex(ValueError, 'could not be confirmed'):
                gr.create_goods_receipt(1, 1, 1, {1: '1'}, submission_id=str(uuid.uuid4()))
        connect.assert_called_once()
        connection.commit.assert_called_once()

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
            with self.subTest(errno=errno), patch.object(gr, '_create_goods_receipt_transaction', side_effect=[gr._RetryableReceiptError(),expected]) as transaction:
                self.assertEqual(gr.create_goods_receipt(1,1,1,{'3':'1.25'},submission_id=token),expected)
                self.assertEqual(transaction.call_count,2)
                self.assertEqual(transaction.call_args_list[0],transaction.call_args_list[1])
                self.assertEqual(transaction.call_args.args[-1],token)

    def test_lock_retries_are_bounded(self):
        with patch.object(gr, '_create_goods_receipt_transaction', side_effect=gr._RetryableReceiptError()) as transaction:
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
