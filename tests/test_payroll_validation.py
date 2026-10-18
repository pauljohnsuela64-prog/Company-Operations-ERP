"""Payroll money boundaries; no database configuration is used."""
from decimal import Decimal
from datetime import date
import hashlib
import json
import unittest
from unittest.mock import Mock, patch

from payroll_validation import MAX_MONEY, payroll_money, validate_payroll_totals, validate_evidence_money
import payroll_adjustment_repository as adjustments
import payroll_repository as compensation
import payroll_period_repository as periods
from payroll_calculation_repository import _money
from payroll_freshness import fingerprint, _json_value


class PayrollMoneyTests(unittest.TestCase):
    def test_exact_boundaries(self):
        for value in ('0.01', '1', '1.20', ' 1.23 ', '9999999999.99', Decimal('12.34')):
            self.assertEqual(payroll_money(value), Decimal(str(value).strip()))
        self.assertEqual(payroll_money('0', allow_zero=True), 0)

    def test_invalid_inputs(self):
        for value in ('', 'abc', '1_000', '1,000', 'NaN', 'sNaN', 'Infinity', '-Infinity',
                      '-1', '0', '0.001', '1.000', '9999999999.995', '10000000000',
                      '1e99999', None, 1.2, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                payroll_money(value)

    def test_aggregate_capacity(self):
        validate_payroll_totals(gross_pay=MAX_MONEY, net_pay=Decimal('0'))
        for name in ('additional_earnings', 'other_deductions', 'gross_pay', 'total_deductions', 'net_pay'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_payroll_totals(**{name: MAX_MONEY + Decimal('.01')})

    def test_existing_half_up_is_preserved_but_rounded_overflow_is_rejected(self):
        self.assertEqual(_money(Decimal('1.005')), Decimal('1.01'))
        with self.assertRaises(ValueError):
            validate_payroll_totals(gross_pay=_money(Decimal('9999999999.995')))

    def test_legacy_clipped_values_cannot_be_accepted_as_valid_evidence(self):
        entry = dict(basic_rate=Decimal('1000'), daily_rate=Decimal('100'),
                     regular_pay=Decimal('500'), additional_earnings=MAX_MONEY,
                     gross_pay=MAX_MONEY, attendance_deduction=Decimal('0'),
                     total_deductions=Decimal('0'), net_pay=MAX_MONEY)
        with self.assertRaises(ValueError):
            validate_evidence_money(entry, [dict(adjustment_type='EARNING', amount=MAX_MONEY)] * 2)

    def test_valid_version_one_fingerprint_payload_is_unchanged(self):
        entry = dict(basic_rate=Decimal('1000'), daily_rate=Decimal('100'),
                     regular_pay=Decimal('500'), additional_earnings=Decimal('0'),
                     gross_pay=Decimal('500'), attendance_deduction=Decimal('0'),
                     total_deductions=Decimal('0'), net_pay=Decimal('500'), employee_id=9)
        period = dict(start_date=date(2026,1,5), end_date=date(2026,1,9))
        cursor = Mock(); cursor.fetchone.side_effect = [period, entry]
        cursor.fetchall.side_effect = [[], [], []]
        old_payload = dict(version=1, period=period, entry=entry, attendance=[], leaves=[], adjustments=[])
        expected = hashlib.sha256(json.dumps(old_payload, default=_json_value, sort_keys=True,
                                             separators=(',', ':')).encode('utf-8')).hexdigest()
        self.assertEqual(fingerprint(cursor, 1, 2), expected)

    def test_repository_validation_precedes_connection(self):
        with patch.object(compensation, 'get_connection') as connect:
            for fn in (compensation.create_employee_compensation, compensation.update_employee_compensation):
                with self.assertRaises(ValueError):
                    fn(1, 'MONTHLY', Decimal('0.001'), '2026-01-01', None, 7)
            connect.assert_not_called()
        with patch.object(adjustments, 'get_connection') as connect:
            with self.assertRaises(ValueError):
                adjustments.add_payroll_adjustment(1, 'EARNING', 'Test', '1.001', None, 7)
            connect.assert_not_called()

    def test_projected_overflow_never_updates_or_inserts(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [dict(regular_pay=Decimal('1'), attendance_deduction=0),
                                      dict(earnings=MAX_MONEY, deductions=0)]
        with self.assertRaisesRegex(ValueError, 'Gross pay'):
            adjustments._refresh_payroll_entry_totals(cursor, 1, persist=False)
        self.assertTrue(all(call.args[0].lstrip().startswith('SELECT') for call in cursor.execute.call_args_list))

    def test_adjustment_parent_before_child_locks(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [dict(payroll_period_id=2), dict(status='DRAFT'),
                                      dict(payroll_entry_id=1, entry_status='CALCULATED')]
        self.assertEqual(adjustments._lock_adjustment_entry(cursor, 1)['period_status'], 'DRAFT')
        queries = [' '.join(call.args[0].split()) for call in cursor.execute.call_args_list]
        self.assertNotIn('FOR UPDATE', queries[0])
        self.assertIn('FROM payroll_periods', queries[1])
        self.assertIn('FROM payroll_entries', queries[2])
        self.assertTrue(all('FOR UPDATE' in q for q in queries[1:]))

    def test_overlap_current_read_and_cancelled_exclusion(self):
        cursor = Mock(); cursor.fetchone.return_value = None
        periods._reject_overlap(cursor, '2026-01-01', '2026-01-15', 7)
        query, params = cursor.execute.call_args.args
        self.assertIn("status <> 'CANCELLED'", query)
        self.assertIn('FOR UPDATE', query)
        self.assertEqual(params, ('2026-01-15', '2026-01-01', 7, 7))
        cursor.fetchone.return_value = (1,)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            periods._reject_overlap(cursor, '2026-01-01', '2026-01-15')
