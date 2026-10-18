"""Schema-specific IT asset validation boundaries, with no database access."""
from datetime import date, datetime
from decimal import Decimal
import unittest

from it_asset_validation import asset_values, calendar_date, cost, identifier, text


class AssetValidationTests(unittest.TestCase):
    def values(self, **changes):
        fields = dict(asset_tag=' it-1 ', asset_name='Laptop', category_id='1', brand='', model='',
                      serial_number='', department_id='', purchase_date='', purchase_cost='',
                      warranty_expiry='', condition_status='good', notes='')
        fields.update(changes)
        return asset_values(fields)

    def test_exact_decimal_zero_maximum_and_optional_cost(self):
        for raw, expected in [('',None),(None,None),('0',Decimal('0')),('0.00',Decimal('0.00')),
                              ('0.10',Decimal('0.10')),('9,999,999,999.99',Decimal('9999999999.99'))]:
            self.assertEqual(cost(raw), expected)

    def test_invalid_costs_never_round_or_overflow(self):
        for raw in ['NaN','sNaN','Infinity','-Infinity','-0.01','-0.00','1.001','1.000','10000000000',
                    '1e2','1,00','1,2345',Decimal('NaN'),Decimal('Infinity'),0.1,True]:
            with self.subTest(raw=str(raw)), self.assertRaises(ValueError):
                cost(raw)

    def test_calendar_dates_and_schema_boundaries(self):
        for raw in ['1000-01-01','9999-12-31','2024-02-29']:
            self.assertEqual(calendar_date(raw,'Date'), date.fromisoformat(raw))
        self.assertIsNone(calendar_date('', 'Date', True))
        for raw in ['',None,'0000-01-01','0999-12-31','2026-02-29','2026-13-01','2026-1-1',datetime(2026,1,1)]:
            with self.subTest(raw=str(raw)), self.assertRaises(ValueError):
                calendar_date(raw,'Date')

    def test_all_asset_text_boundaries_and_required_fields(self):
        for field, length in [('asset_tag',50),('asset_name',150),('brand',100),('model',100),('serial_number',100),('notes',255)]:
            self.values(**{field:'x'*length})
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.values(**{field:'x'*(length+1)})
        for field in ['asset_tag','asset_name','category_id','condition_status']:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.values(**{field:''})
        # Unicode uppercasing can expand a tag beyond its VARCHAR limit.
        with self.assertRaises(ValueError): self.values(asset_tag='ß'*26)
        self.assertEqual(self.values()[0], 'IT-1')

    def test_identifiers_and_condition_enum(self):
        self.assertEqual(identifier('2147483647','ID'),2147483647)
        self.assertIsNone(identifier('', 'ID', True))
        for raw in ['0','-1','1.0','1e2','2147483648','1'*5000,True]:
            with self.subTest(raw=str(raw)[:20]), self.assertRaises(ValueError): identifier(raw,'ID')
        with self.assertRaises(ValueError): self.values(condition_status='UNKNOWN')

    def test_no_unapproved_date_ordering_or_future_date_rule(self):
        values = self.values(purchase_date='2027-01-01', warranty_expiry='2020-01-01', purchase_cost='0.00')
        self.assertEqual(values[7],date(2027,1,1))
        self.assertEqual(values[9],date(2020,1,1))
        self.assertEqual(values[8],Decimal('0.00'))

    def test_maintenance_varchar_boundaries(self):
        for label, limit in [('Maintenance type',50),('Description',255),('Vendor',150),('Notes',255)]:
            self.assertEqual(len(text('a'*limit,label,limit)),limit)
            with self.assertRaises(ValueError): text('a'*(limit+1),label,limit)


if __name__ == '__main__':
    unittest.main()
