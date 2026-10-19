"""Explicitly hypothetical synthetic cases. No configured database is used."""
from calendar import monthrange
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime
from decimal import Decimal, Inexact, Rounded, ROUND_DOWN, localcontext
from fractions import Fraction
import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest

import payroll_monthly_prototype as prototype


def hypothetical_policy():
    # Deliberately explicit independent fixture, not a default production policy.
    return prototype.HypotheticalPolicy(
        scenario='HYPOTHETICAL_MONTHLY_V1', development_only=True, frequency='SEMI_MONTHLY',
        calculator_key='HYPOTHETICAL_MONTHLY_PROTOTYPE_V1', calendar_key='SEMI_MONTHLY_1_15_16_EOM_V1',
        pay_type='MONTHLY', currency_code='PHP', working_week_mask=31,
        cutoff_a_start=1, cutoff_a_end=15, cutoff_b_start=16, cutoff_b_end='MONTH_END',
        full_cutoff_divisor=2, rounding_mode='ROUND_HALF_UP', rounding_scale=2,
        late_treatment='NO_DEDUCTION', absence_treatment='PERIOD_WORKDAY_DIVISOR',
        half_day_treatment='HALF_DAY_DEDUCTION', paid_leave_treatment='NO_DEDUCTION',
        unpaid_leave_treatment='PERIOD_WORKDAY_DIVISOR', missing_evidence='BLOCK',
        proration='BLOCK', calendar_exceptions='BLOCK', odd_cent_handling='BLOCK', excess_deductions='BLOCK')


def synthetic_input(year=2035, month=1, code='A', salary=Decimal('30000.00')):
    start = date(year, month, 1 if code == 'A' else 16)
    end = date(year, month, 15 if code == 'A' else monthrange(year, month)[1])
    cutoff = prototype.Cutoff(code, start, end)
    # Independent enumeration using ordinal weekdays, without calculator helpers.
    scheduled = tuple(date.fromordinal(n) for n in range(start.toordinal(), end.toordinal()+1)
                      if date.fromordinal(n).isoweekday() <= 5)
    eligibility = prototype.SyntheticEligibility(
        fixture_reference='SYNTHETIC:FULL-CUTOFF-001', development_only=True, eligibility='FULL_CUTOFF',
        cutoff=cutoff, hire_date=date(1000, 1, 1), employment_coverage_start=start,
        employment_coverage_end=end, compensation_coverage_start=start, compensation_coverage_end=end,
        employment_reference='SYNTHETIC:EMPLOYMENT-001', compensation_reference='SYNTHETIC:RATE-001',
        pay_type='MONTHLY', currency_code='PHP', scheduled_dates=scheduled, calendar_exceptions=())
    return prototype.CalculationInput(hypothetical_policy(), cutoff, eligibility, salary,
        tuple(prototype.AttendanceDay(day, 'PRESENT') for day in scheduled), (), ())


def statuses(inputs, *values):
    rows = list(inputs.attendance)
    for index, value in enumerate(values): rows[index] = replace(rows[index], status=value)
    return replace(inputs, attendance=tuple(rows))


def leave_input(paid):
    inputs = statuses(synthetic_input(), 'ON_LEAVE')
    leave = prototype.ApprovedLeaveDay(inputs.attendance[0].date, paid, True, 'SYNTHETIC:LEAVE-001')
    return replace(inputs, approved_leave=(leave,))


def adjustment(kind, amount, reference='SYNTHETIC:ADJUSTMENT-001'):
    return prototype.SyntheticAdjustment(kind, Decimal(amount), True, reference)


def independently_rounded_cents(base_cents, units, scheduled):
    """Integer/Fraction oracle, independent of Decimal division/quantize."""
    cents = Fraction(base_cents) * Fraction(units) / scheduled
    quotient, remainder = divmod(cents.numerator, cents.denominator)
    return Decimal(quotient + (2 * remainder >= cents.denominator)) / 100


class MonthlyPrototypeTests(unittest.TestCase):
    def test_a_full_attendance(self):
        result = prototype.calculate(synthetic_input())
        self.assertEqual(result.scheduled_work_days, 11)
        self.assertEqual(result.present_days, 11)
        self.assertEqual(result.regular_pay, Decimal('15000.00'))
        self.assertEqual(result.daily_rate, Decimal('1363.64'))
        self.assertEqual(result.attendance_deduction, Decimal('0.00'))
        self.assertEqual(result.net_pay, Decimal('15000.00'))
        self.assertEqual((result.daily_rate_numerator, result.daily_rate_denominator), (Decimal('15000.00'), 11))
        self.assertEqual(len(result.daily_calculation_rate.as_tuple().digits), 50)

    def test_b_absence(self):
        result = prototype.calculate(statuses(synthetic_input(), 'ABSENT'))
        self.assertEqual((result.absent_days, result.deductible_day_equivalents), (1, Decimal('1')))
        self.assertEqual(result.attendance_deduction, Decimal('1363.64'))
        self.assertEqual(result.net_pay, Decimal('13636.36'))

    def test_c_half_day(self):
        result = prototype.calculate(statuses(synthetic_input(), 'HALF_DAY'))
        self.assertEqual((result.half_day_count, result.deductible_day_equivalents), (1, Decimal('0.5')))
        self.assertEqual(result.attendance_deduction, Decimal('681.82'))
        self.assertEqual(result.net_pay, Decimal('14318.18'))

    def test_d_paid_leave(self):
        result = prototype.calculate(leave_input(True))
        self.assertEqual((result.paid_leave_days, result.unpaid_leave_days), (1, 0))
        self.assertEqual(result.attendance_deduction, Decimal('0.00'))
        self.assertEqual(result.net_pay, Decimal('15000.00'))
        self.assertEqual(result.daily[0].leave_reference, 'SYNTHETIC:LEAVE-001')

    def test_e_unpaid_leave(self):
        result = prototype.calculate(leave_input(False))
        self.assertEqual((result.paid_leave_days, result.unpaid_leave_days), (0, 1))
        self.assertEqual(result.attendance_deduction, Decimal('1363.64'))
        self.assertEqual(result.net_pay, Decimal('13636.36'))

    def test_f_late(self):
        result = prototype.calculate(statuses(synthetic_input(), 'LATE'))
        self.assertEqual(result.late_days, 1)
        self.assertEqual(result.attendance_deduction, Decimal('0.00'))
        self.assertEqual(result.net_pay, Decimal('15000.00'))

    def test_g_earnings_and_deductions(self):
        inputs = replace(synthetic_input(), adjustments=(adjustment('EARNING', '500'),
            adjustment('DEDUCTION', '300', 'SYNTHETIC:ADJUSTMENT-002')))
        result = prototype.calculate(inputs)
        self.assertEqual(result.additional_earnings, Decimal('500.00'))
        self.assertEqual(result.other_deductions, Decimal('300.00'))
        self.assertEqual(result.gross_pay, Decimal('15500.00'))
        self.assertEqual(result.total_deductions, Decimal('300.00'))
        self.assertEqual(result.net_pay, Decimal('15200.00'))

    def test_h_odd_cent_no_invented_balancing(self):
        for salary in ('30000.01', '0.01', '9999999999.99'):
            with self.subTest(salary=salary), self.assertRaisesRegex(prototype.UnsupportedPolicyError, 'Odd-cent.*reconciliation'):
                prototype.calculate(replace(synthetic_input(), monthly_salary=Decimal(salary)))

    def test_i_excess_deduction_and_exact_zero(self):
        inputs = replace(synthetic_input(), adjustments=(adjustment('DEDUCTION', '15000.01'),))
        with self.assertRaisesRegex(prototype.UnsupportedPolicyError, 'exceed gross.*zero-floor'):
            prototype.calculate(inputs)
        result = prototype.calculate(replace(inputs, adjustments=(adjustment('DEDUCTION', '15000'),)))
        self.assertEqual(result.net_pay, Decimal('0.00'))
        result = prototype.calculate(statuses(synthetic_input(), *(['ABSENT'] * 11)))
        self.assertEqual((result.attendance_deduction, result.net_pay), (Decimal('15000.00'), Decimal('0.00')))

    def test_j_mid_cutoff_hire(self):
        inputs = synthetic_input()
        with self.assertRaisesRegex(prototype.UnsupportedPolicyError, 'Mid-cutoff.*proration'):
            prototype.calculate(replace(inputs, eligibility=replace(inputs.eligibility, hire_date=date(2035, 1, 2))))

    def test_k_l_unsupported_pay_types_and_currency(self):
        inputs = synthetic_input()
        for pay_type, currency in (('DAILY', 'PHP'), ('HOURLY', 'PHP'), ('MONTHLY', 'USD'), ('', 'PHP')):
            with self.subTest(pay_type=pay_type, currency=currency), self.assertRaisesRegex(prototype.UnsupportedPolicyError, 'MONTHLY/PHP'):
                prototype.calculate(replace(inputs, eligibility=replace(inputs.eligibility, pay_type=pay_type, currency_code=currency)))

    def test_m_missing_or_conflicting_attendance_leave(self):
        inputs = synthetic_input(); on_leave = statuses(inputs, 'ON_LEAVE')
        leave = prototype.ApprovedLeaveDay(inputs.attendance[0].date, True, True, 'SYNTHETIC:LEAVE-001')
        cases = (
            replace(inputs, attendance=inputs.attendance[:-1]), on_leave,
            replace(inputs, approved_leave=(leave,)),
            replace(on_leave, approved_leave=(leave, leave)),
            replace(inputs, attendance=inputs.attendance + (inputs.attendance[0],)),
            replace(on_leave, approved_leave=(replace(leave, approved=False),)),
            replace(on_leave, approved_leave=(replace(leave, is_paid=1),)),
            statuses(inputs, 'HOLIDAY'), statuses(inputs, 'UNKNOWN'))
        for case in cases:
            with self.subTest(case=case.attendance[0]), self.assertRaises(prototype.PrototypeValidationError):
                prototype.calculate(case)

    def test_n_arbitrary_period_rejected(self):
        inputs = synthetic_input()
        for cutoff in (prototype.Cutoff('A', date(2035, 1, 1), date(2035, 1, 5)),
                       prototype.Cutoff('B', date(2035, 1, 16), date(2035, 2, 28)),
                       prototype.Cutoff('A', date(2035, 1, 2), date(2035, 1, 15)),
                       prototype.Cutoff('C', date(2035, 1, 1), date(2035, 1, 15)),
                       prototype.Cutoff('B', date(2035, 1, 16), date(2035, 1, 15))):
            with self.subTest(cutoff=cutoff), self.assertRaises(prototype.UnsupportedPolicyError):
                prototype.calculate(replace(inputs, cutoff=cutoff))

    def test_o_half_cent_below_exact_and_above(self):
        # Base 0.01 / 11: units 5, 5.5, 6 straddle/exactly hit half a cent.
        for days, expected in ((['ABSENT']*5, '0.00'), (['ABSENT']*5+['HALF_DAY'], '0.01'), (['ABSENT']*6, '0.01')):
            inputs = statuses(synthetic_input(salary=Decimal('0.02')), *days)
            with self.subTest(days=days):
                result = prototype.calculate(inputs)
                self.assertEqual(result.attendance_deduction, Decimal(expected))
        # Multiplying a rounded 50-digit repeating rate can obscure this exact tie;
        # aggregate numerator FIRST: (0.03 * 5.5) / 11 = 0.015 -> 0.02.
        result = prototype.calculate(statuses(synthetic_input(salary=Decimal('0.06')), *(['ABSENT']*5+['HALF_DAY'])))
        self.assertEqual(result.attendance_deduction, Decimal('0.02'))
        self.assertEqual(result.daily_rate, Decimal('0.00'))

    def test_o_money_boundaries_and_overflow(self):
        inputs = synthetic_input(salary=Decimal('9999999999.98'))
        self.assertEqual(prototype.calculate(inputs).regular_pay, Decimal('4999999999.99'))
        edge = replace(inputs, adjustments=(adjustment('EARNING', '5000000000.00'),))
        self.assertEqual(prototype.calculate(edge).gross_pay, Decimal('9999999999.99'))
        for case in (replace(inputs, monthly_salary=Decimal('10000000000.00')),
                     replace(inputs, adjustments=(adjustment('EARNING', '5000000000.01'),)),
                     replace(inputs, adjustments=(adjustment('EARNING', '9999999999.99'), adjustment('EARNING', '0.01', 'SYNTHETIC:OVERFLOW'))),
                     replace(inputs, adjustments=(adjustment('DEDUCTION', '9999999999.99'), adjustment('DEDUCTION', '0.01', 'SYNTHETIC:OVERFLOW'))),
                     replace(statuses(inputs, 'ABSENT'), adjustments=(adjustment('DEDUCTION', '9999999999.99'),))):
            with self.subTest(case=case.adjustments), self.assertRaisesRegex(prototype.PrototypeValidationError, 'database limit'):
                prototype.calculate(case)

    def test_exact_aggregation_not_display_rate_times_units(self):
        result = prototype.calculate(statuses(synthetic_input(), 'ABSENT', 'ABSENT', 'ABSENT'))
        self.assertEqual(result.attendance_deduction, Decimal('4090.91'))
        self.assertEqual(result.daily_rate*3, Decimal('4090.92'))
        result = prototype.calculate(statuses(synthetic_input(), 'ABSENT', 'ABSENT', 'HALF_DAY'))
        self.assertEqual(result.attendance_deduction, Decimal('3409.09'))
        self.assertEqual(result.net_pay, Decimal('11590.91'))

    def test_rational_oracle_all_cutoffs_and_deductible_units(self):
        # Independent integer/Fraction rounding for every possible half-day unit
        # total, on every cutoff in a leap year, including small and large salaries.
        for month in range(1, 13):
            for code in ('A', 'B'):
                for salary in ('0.02', '0.06', '12345.68', '30000.00', '9999999999.98'):
                    inputs = synthetic_input(2028, month, code, Decimal(salary))
                    count = len(inputs.attendance)
                    for half_units in range(2*count+1):
                        days = ['ABSENT']*(half_units//2)+(['HALF_DAY'] if half_units%2 else [])
                        result = prototype.calculate(statuses(inputs, *days))
                        expected = independently_rounded_cents(int(Decimal(salary)*50), Fraction(half_units, 2), count)
                        self.assertEqual(result.attendance_deduction, expected, (month, code, salary, half_units))

    def test_leap_year_month_end_and_calendar_limits(self):
        for year, month, code, end, count in ((2028, 2, 'A', 15, 11), (2028, 2, 'B', 29, 10),
                (2027, 2, 'B', 28, 9), (2100, 2, 'B', 28, 9), (2000, 2, 'B', 29, 10),
                (2026, 4, 'B', 30, 11), (2035, 1, 'B', 31, 12), (9999, 12, 'B', 31, 12)):
            with self.subTest(year=year, month=month):
                result = prototype.calculate(synthetic_input(year, month, code))
                self.assertEqual(result.cutoff.end_date.day, end)
                self.assertEqual(result.scheduled_work_days, count)
                self.assertTrue(all(day.weekday()<5 for day in result.scheduled_dates))

    def test_incomplete_eligibility_and_coverage(self):
        inputs = synthetic_input()
        for name, value in (('eligibility', 'UNKNOWN'), ('development_only', False), ('hire_date', None),
                ('employment_coverage_start', None), ('employment_coverage_end', date(2035, 1, 14)),
                ('compensation_coverage_start', date(2035, 1, 2)), ('compensation_coverage_end', None),
                ('fixture_reference', 'real employee'), ('employment_reference', ''),
                ('compensation_reference', 'SYNTHETIC:'), ('scheduled_dates', inputs.eligibility.scheduled_dates[:-1]),
                ('scheduled_dates', inputs.eligibility.scheduled_dates+(inputs.eligibility.scheduled_dates[0],)),
                ('calendar_exceptions', ('HOLIDAY',)), ('calendar_exceptions', ('SPECIAL_PAY',))):
            with self.subTest(field=name, value=value), self.assertRaises(prototype.PrototypeValidationError):
                prototype.calculate(replace(inputs, eligibility=replace(inputs.eligibility, **{name:value})))
        other = synthetic_input(2035, 1, 'B').cutoff
        with self.assertRaisesRegex(prototype.PrototypeValidationError, 'exact requested cutoff'):
            prototype.calculate(replace(inputs, eligibility=replace(inputs.eligibility, cutoff=other)))

    def test_unsupported_policy_fields_values_and_formulas(self):
        inputs = synthetic_input()
        for field in fields(prototype.HypotheticalPolicy):
            current = getattr(inputs.policy, field.name)
            value = not current if type(current) is bool else current+1 if type(current) is int else 'UNSUPPORTED'
            with self.subTest(field=field.name), self.assertRaisesRegex(prototype.UnsupportedPolicyError, field.name):
                prototype.calculate(replace(inputs, policy=replace(inputs.policy, **{field.name:value})))
        values = {field.name:getattr(inputs.policy,field.name) for field in fields(prototype.HypotheticalPolicy)}
        with self.assertRaisesRegex(TypeError, "unexpected keyword argument 'formula'"):
            prototype.HypotheticalPolicy(**values, formula='eval(formula)')
        with self.assertRaises(prototype.PrototypeValidationError):prototype.calculate(replace(inputs, policy={'formula':'salary/2'}))
        with self.assertRaises(prototype.UnsupportedPolicyError):prototype.calculate(replace(inputs, policy=replace(inputs.policy, full_cutoff_divisor=True)))

    def test_invalid_monetary_inputs(self):
        for value in (0, 1.0, True, '30000.00', None, Decimal('NaN'), Decimal('sNaN'),
                      Decimal('Infinity'), Decimal('-Infinity'), Decimal('-1'), Decimal('0'),
                      Decimal('-0.00'), Decimal('30000.000'), Decimal('1E-9999'), Decimal('1E9999')):
            with self.subTest(value=str(value)), self.assertRaises(prototype.PrototypeValidationError):
                prototype.calculate(replace(synthetic_input(), monthly_salary=value))
        for value in (Decimal('NaN'), Decimal('Infinity'), Decimal('0'), Decimal('-1'),
                      Decimal('1.001'), Decimal('10000000000.00'), 1.0, '500'):
            with self.subTest(adjustment=str(value)), self.assertRaises(prototype.PrototypeValidationError):
                prototype.calculate(replace(synthetic_input(), adjustments=(prototype.SyntheticAdjustment('EARNING', value, True, 'SYNTHETIC:INVALID'),)))

    def test_invalid_adjustments_and_approval(self):
        row = adjustment('EARNING', '500')
        for rows in ((replace(row, kind='OVERTIME'),), (replace(row, approved=False),),
                     (replace(row, approved=1),), (replace(row, fixture_reference='company record'),), (row, row)):
            with self.subTest(rows=rows), self.assertRaises(prototype.PrototypeValidationError):
                prototype.calculate(replace(synthetic_input(), adjustments=rows))

    def test_dates_outside_schedule_or_wrong_types(self):
        inputs = synthetic_input()
        for value in (date(999, 1, 1), datetime(2035, 1, 1), '2035-01-01', None):
            with self.subTest(date=value), self.assertRaises(prototype.PrototypeValidationError):
                prototype.calculate(replace(inputs, cutoff=replace(inputs.cutoff, start_date=value)))
        for day in (date(2035, 1, 6), date(2035, 1, 16)):
            with self.assertRaises(prototype.PrototypeValidationError):
                prototype.calculate(replace(inputs, attendance=inputs.attendance+(prototype.AttendanceDay(day, 'PRESENT'),)))
        for name in ('attendance', 'approved_leave', 'adjustments'):
            with self.subTest(field=name), self.assertRaises(prototype.PrototypeValidationError):
                prototype.calculate(replace(inputs, **{name:list(getattr(inputs, name))}))
        with self.assertRaises(prototype.PrototypeValidationError):prototype.calculate({})

    def test_determinism_order_independence_immutability_and_outputs(self):
        inputs = replace(leave_input(True), adjustments=(adjustment('EARNING','500','SYNTHETIC:Z'),adjustment('DEDUCTION','300','SYNTHETIC:A')))
        result = prototype.calculate(inputs)
        reordered = replace(inputs, attendance=tuple(reversed(inputs.attendance)),
            adjustments=tuple(reversed(inputs.adjustments)),
            eligibility=replace(inputs.eligibility, scheduled_dates=tuple(reversed(inputs.eligibility.scheduled_dates))))
        self.assertEqual(result, prototype.calculate(reordered))
        self.assertEqual(hash(result), hash(prototype.calculate(inputs)))
        with self.assertRaises(FrozenInstanceError):result.net_pay = Decimal('1')
        with self.assertRaises(FrozenInstanceError):result.daily[0].classification = 'ABSENT'
        with self.assertRaises(FrozenInstanceError):result.adjustments[0].amount = Decimal('1')
        with self.assertRaises(FrozenInstanceError):result.cutoff.code = 'B'
        import payroll_evidence
        outputs = result.as_evidence_outputs()
        self.assertEqual(set(outputs), set(payroll_evidence.MONEY_FIELDS+payroll_evidence.COUNT_FIELDS))
        self.assertEqual(len(outputs), 15)
        outputs['net_pay'] = Decimal('1')
        self.assertEqual(result.net_pay, Decimal('15200.00'))
        self.assertEqual(result.explanation[-1].value, result.net_pay)

    def test_decimal_context_independence_and_no_global_mutation(self):
        inputs = statuses(synthetic_input(), 'ABSENT', 'HALF_DAY')
        expected = prototype.calculate(inputs)
        with localcontext() as ctx:
            ctx.prec = 2; ctx.rounding = ROUND_DOWN
            ctx.traps[Inexact] = True; ctx.traps[Rounded] = True
            before = ctx.copy()
            self.assertEqual(prototype.calculate(inputs), expected)
            self.assertEqual((ctx.prec, ctx.rounding, ctx.flags, ctx.traps),
                             (before.prec, before.rounding, before.flags, before.traps))

    def test_production_import_isolation_and_no_import_side_effects(self):
        root = Path(__file__).resolve().parents[1]
        production = [p for p in root.glob('*.py') if p.name != 'payroll_monthly_prototype.py']
        for path in production:
            self.assertNotIn('payroll_monthly_prototype', path.read_text(encoding='utf-8-sig'), path.name)
        # Fresh interpreter: deny application/DB/network imports, file writes,
        # network calls and subprocesses before import AND calculation.
        code = '''
import sys, importlib.abc
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'app','database','flask','mysql','sqlite3','socket'} or fullname.endswith('_repository'):
            raise AssertionError('Forbidden import: '+fullname)
sys.meta_path.insert(0,Deny())
def audit(event,args):
    if event in {'socket.connect','subprocess.Popen','os.system','os.remove','os.mkdir','os.rename'}:
        raise AssertionError('Forbidden side effect: '+event)
    if event=='open':
        mode=args[1];flags=args[2]
        if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or flags & (1|2|64|512|1024):
            raise AssertionError('File write forbidden')
sys.addaudithook(audit)
import payroll_monthly_prototype as p
assert not any(n in sys.modules for n in ('app','database','flask','mysql','payroll_evidence_repository'))
from test_payroll_monthly_prototype import synthetic_input
assert p.calculate(synthetic_input()).net_pay.as_tuple().exponent==-2
'''
        # Avoid importing this unittest module in that interpreter, since its
        # unittest dependency legitimately imports sockets on some Python builds.
        setup = Path(__file__).read_text().split('class MonthlyPrototypeTests')[0]
        setup = setup[setup.index('def hypothetical_policy():'):]
        code = code.replace('from test_payroll_monthly_prototype import synthetic_input',
            'from calendar import monthrange\nfrom datetime import date\nfrom decimal import Decimal\nprototype=p\n'+setup)
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=root,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(result.stdout, '')
        # No implicit clock or dynamic formula/configuration execution.
        tree = ast.parse((root/'payroll_monthly_prototype.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                self.assertNotIn(getattr(node.func,'id',''), ('eval','exec','open','__import__'))
                self.assertNotIn(getattr(node.func,'attr',''), ('today','now','utcnow','connect','execute'))


if __name__ == '__main__': unittest.main()
