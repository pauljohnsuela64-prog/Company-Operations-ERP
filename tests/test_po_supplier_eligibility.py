"""Repository boundaries; no configured database connections are permitted."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import MagicMock, patch


class POSupplierEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = ExitStack()
        cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv', return_value=False))
        cls.guard.enter_context(patch('mysql.connector.connect', side_effect=AssertionError('Company DB forbidden')))
        cls.repo = importlib.import_module('purchase_order_repository')

    def test_invalid_supplier_ids_fail_before_connection(self):
        for value in (None, '', True, False, 0, -1, '1.0', 1.0, 'bad', '1 OR 1=1', 2147483648):
            with self.subTest(value=value), patch.object(self.repo, 'get_connection') as connect:
                with self.assertRaises(ValueError):
                    self.repo.create_purchase_order_from_request(1, value, 1)
                connect.assert_not_called()

    def test_missing_and_inactive_supplier_roll_back_without_inserts(self):
        for supplier in (None, (0,)):
            with self.subTest(supplier=supplier):
                connection = MagicMock()
                cursor = connection.cursor.return_value
                cursor.fetchone.side_effect = [('APPROVED',), None, supplier]
                with patch.object(self.repo, 'get_connection', return_value=connection):
                    with self.assertRaisesRegex(ValueError, 'invalid or inactive'):
                        self.repo.create_purchase_order_from_request(1, 7, 1)
                connection.rollback.assert_called_once()
                connection.commit.assert_not_called()
                self.assertFalse(any('INSERT' in call.args[0] for call in cursor.execute.call_args_list))
                cursor.close.assert_called_once()
                connection.close.assert_called_once()

    def test_parent_and_duplicate_guards_precede_supplier_lock(self):
        for rows, message in (([None], 'not found'), ([('DRAFT',)], 'approved'),
                              ([('APPROVED',), (3,)], 'already exists')):
            with self.subTest(message=message):
                connection = MagicMock()
                cursor = connection.cursor.return_value
                cursor.fetchone.side_effect = rows
                with patch.object(self.repo, 'get_connection', return_value=connection):
                    with self.assertRaisesRegex(ValueError, message):
                        self.repo.create_purchase_order_from_request(1, 7, 1)
                self.assertFalse(any('FROM suppliers' in call.args[0] for call in cursor.execute.call_args_list))
                connection.rollback.assert_called_once()


if __name__ == '__main__':
    unittest.main()
