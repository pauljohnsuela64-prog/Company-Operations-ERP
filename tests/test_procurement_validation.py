"""Procurement numeric boundaries; integration coverage is in mysql_procurement_smoke.py."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from procurement_validation import decimal_value, validate_notes
import purchase_request_repository as pr
import purchase_order_repository as po


class ProcurementValidationTests(unittest.TestCase):
    def test_decimal_boundaries_preserve_exact_values(self):
        for value in ('0', '0.01', '9999999999.99', '1.20'):
            with self.subTest(value=value):
                self.assertEqual(decimal_value(value, 'Cost'), Decimal(value))
                self.assertIsInstance(decimal_value(value, 'Cost'), Decimal)
        self.assertEqual(decimal_value('0.01', 'Quantity', positive=True), Decimal('0.01'))

    def test_invalid_numbers_do_not_open_write_connections(self):
        for value in ('NaN', 'sNaN', 'Infinity', '-Infinity', '-0.01', '1.001', '10000000000', '1e10000', '', None):
            with self.subTest(value=value), patch.object(po, 'get_connection') as connect:
                with self.assertRaises(ValueError):
                    po.update_purchase_order_item_cost(1, value)
                connect.assert_not_called()
            with self.subTest(value=value), patch.object(pr, 'get_connection') as connect:
                with self.assertRaises(ValueError):
                    pr.add_purchase_request_item(1, 1, value)
                connect.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'greater than zero'):
            decimal_value('0', 'Quantity', positive=True)

    def test_notes_limits_apply_before_write_connections(self):
        validate_notes('x' * 255, 'Notes')
        for action, module in ((lambda: po.create_purchase_order_from_request(1,1,1,notes='x'*256), po),
                               (lambda: pr.reject_purchase_request(1,'x'*256), pr)):
            with patch.object(module, 'get_connection') as connect:
                with self.assertRaisesRegex(ValueError, '255 characters'):
                    action()
                connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
