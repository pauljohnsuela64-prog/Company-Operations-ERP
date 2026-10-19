import unittest
from datetime import date, datetime
from unittest.mock import Mock, patch
import payroll_generation_repository as generation
from payroll_freshness import raise_payroll_lock_error


class CutoffTests(unittest.TestCase):
    def test_calendar_boundaries(self):
        for year,month,last in [(2027,2,28),(2028,2,29),(2026,4,30),(2026,1,31),
                                 (2026,12,31),(2027,1,31),(1000,1,31),(9999,12,31)]:
            a,b=generation.month_cutoffs(year,month)
            self.assertEqual((a['start_date'],a['end_date']),(date(year,month,1),date(year,month,15)))
            self.assertEqual((b['start_date'],b['end_date']),(date(year,month,16),date(year,month,last)))

    def test_invalid_calendar(self):
        for year,month in [(999,1),(10000,1),(2026,0),(2026,13),('NaN',1),(True,1),(2026,'1.5')]:
            with self.assertRaises(ValueError):generation.month_cutoffs(year,month)

    def test_explicit_payment_dates(self):
        end=date(2028,2,29)
        for value in ['',None,'2028-02-30','2028-02-28','20280229',datetime(2028,2,29), '0999-01-01']:
            with self.assertRaises(ValueError):generation.payment_date(value,end,'Payment')
        self.assertEqual(generation.payment_date('2028-02-29',end,'Payment'),end)
        self.assertEqual(generation.payment_date('2028-03-01',end,'Payment'),date(2028,3,1))

    def test_boundary_straddling_fails_closed(self):
        cursor=Mock()
        cursor.fetchall.return_value=[dict(effective_from=date(2028,1,1)),dict(effective_from=date(2028,1,10))]
        with patch.object(generation,'_decode',side_effect=lambda row:row):
            with self.assertRaisesRegex(ValueError,'straddle'):
                generation._resolve(cursor,generation.month_cutoffs(2028,1))

    def test_lock_errors_request_retry(self):
        for errno in (1205,1213):
            error=Exception('synthetic lock error');error.errno=errno
            with self.assertRaisesRegex(ValueError,'retry'):raise_payroll_lock_error(error)
