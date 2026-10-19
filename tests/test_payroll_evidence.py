"""Offline wire-contract and frozen version-1 compatibility regressions."""
import copy
from datetime import date,datetime
from decimal import Decimal
import hashlib
import json
import unittest
from unittest.mock import Mock,patch
import payroll_evidence as wire
import payroll_freshness as v1


def fixture(spec=wire.SCHEMA):
    if isinstance(spec,dict):return {k:fixture(v) for k,v in spec.items()}
    if isinstance(spec,list):return []
    if isinstance(spec,tuple):return spec[0]
    if spec.startswith('?'):return None
    return {'id':1,'count':0,'money':Decimal('0.00'),'positive_money':Decimal('1.00'),
            'date':date(2035,1,1),'timestamp':datetime(2035,1,1),
            'hash':'a'*64,'text':'Synthetic approved reference'}[spec]


class EvidenceTests(unittest.TestCase):
    def test_determinism_money_null_and_timestamp(self):
        p=fixture();p['outputs']['regular_pay']=Decimal('1.2')
        encoded=wire.canonical_evidence(p);value=json.loads(encoded)
        self.assertEqual(value['outputs']['regular_pay'],'1.20')
        self.assertEqual(value['inputs']['certification']['certified_at'],'2035-01-01T08:00:00.000000+08:00')
        self.assertEqual(encoded,wire.canonical_evidence(dict(reversed(list(p.items())))))
        self.assertEqual(wire.evidence_digest(p),hashlib.sha256(encoded.encode()).hexdigest())
        member=fixture(wire.MEMBER);member['employee_id']=2
        p['inputs']['roster']=[member,dict(member,employee_id=1)]
        self.assertIsNone(json.loads(wire.canonical_evidence(p))['inputs']['roster'][0]['employment_reference'])
        first=wire.evidence_digest(p);p['inputs']['roster'].reverse()
        self.assertEqual(first,wire.evidence_digest(p))

    def test_bad_money_and_precision_are_rejected(self):
        for amount in (1.0,True,None,'NaN','Infinity',Decimal('NaN'),Decimal('Infinity'),'-1','0.001','10000000000'):
            p=fixture();p['outputs']['regular_pay']=amount
            with self.subTest(amount=str(amount)),self.assertRaises(ValueError):wire.canonical_evidence(p)
        p=fixture();p['outputs']['regular_pay']=Decimal('9999999999.99')
        self.assertIn('9999999999.99',wire.canonical_evidence(p))

    def test_unsupported_keys_values_duplicates_and_versions(self):
        for mutate in (lambda p:p.update(extra=1),lambda p:p['inputs']['policy'].update(calculator_key='exec()'),
                       lambda p:p['outputs'].update(net_pay=object()),lambda p:p.update(format_version=True),
                       lambda p:p['inputs']['calendar'].update(exceptions=[{}]),
                       lambda p:p['inputs']['calendar'].update(scheduled_dates=['2035-01-01']*2),
                       lambda p:p['inputs']['certification'].update(certified_at='2035-01-01T00:00:00'),
                       lambda p:p['inputs']['period'].update(start_date='2035-02-30')):
            p=fixture();mutate(p)
            with self.assertRaises(ValueError):wire.canonical_evidence(p)
        for version in (0,3,None,True,'1'):
            with self.assertRaises(ValueError):wire.fingerprint_for_version(None,1,1,version)
        with patch('payroll_evidence_repository.verify_current',return_value={'evidence_digest':'b'*64}) as verify:
            self.assertEqual(wire.fingerprint_for_version(None,1,2,2),'b'*64)
            verify.assert_called_once_with(None,1,2)

    def test_version_one_frozen_bytes_and_dispatch(self):
        period=dict(start_date=date(2035,1,1),end_date=date(2035,1,15))
        entry=dict(payroll_entry_id=2,employee_id=9,pay_type='MONTHLY',basic_rate=Decimal('1000.00'),currency_code='PHP')
        entry.update({k:Decimal('0.00') for k in wire.MONEY_FIELDS})
        entry.update({k:0 for k in wire.COUNT_FIELDS})
        cursor=Mock();cursor.fetchone.side_effect=[period,entry];cursor.fetchall.side_effect=[[],[],[]]
        # Explicit expected v1 projection/encoding, not the new normalizer.
        expected=json.dumps(dict(version=1,period={'start_date':'2035-01-01','end_date':'2035-01-15'},
            entry={k:(str(v) if isinstance(v,Decimal) else v) for k,v in entry.items()},attendance=[],leaves=[],adjustments=[]),
            sort_keys=True,separators=(',',':'))
        self.assertEqual(wire.fingerprint_for_version(cursor,1,2,1),hashlib.sha256(expected.encode()).hexdigest())
        self.assertEqual(hashlib.sha256(expected.encode()).hexdigest(),
                         'c1e72083d443eb69366a5a85871bba6ec8ba113955732e85dcfd0e554eefac61')
        self.assertEqual(v1.VERSION,1)

    def test_daily_classifications_and_unsupported_conditions(self):
        import payroll_evidence_repository as repository
        period=dict(start_date=date(2035,1,1),end_date=date(2035,1,1))
        policy=dict(attendance_rules=dict(late_treatment='NO_DEDUCTION',absence_treatment='PERIOD_WORKDAY_DIVISOR',
                    half_day_treatment='HALF_DAY_DEDUCTION'),leave_rules=dict(paid_leave_treatment='NO_DEDUCTION',
                    unpaid_leave_treatment='PERIOD_WORKDAY_DIVISOR'))
        attendance=[dict(attendance_id=1,attendance_date=date(2035,1,1),status='PRESENT')]
        for status in ('PRESENT','LATE','ABSENT','HALF_DAY'):
            attendance[0]['status']=status
            self.assertEqual(repository._daily(period,policy,attendance,[])[0]['classification'],status)
        leave=dict(leave_request_id=1,start_date=date(2035,1,1),end_date=date(2035,1,1),total_days=Decimal('1.00'),is_paid=1)
        with self.assertRaisesRegex(ValueError,'conflict'):repository._daily(period,policy,attendance,[leave])
        attendance[0]['status']='ON_LEAVE'
        self.assertEqual(repository._daily(period,policy,attendance,[leave])[0]['classification'],'PAID_LEAVE')
        leave['is_paid']=0
        self.assertEqual(repository._daily(period,policy,attendance,[leave])[0]['classification'],'UNPAID_LEAVE')
        for rows,leaves in (([],[]),(attendance,[]),(attendance,[leave,dict(leave,leave_request_id=2)]),
                            (attendance,[dict(leave,total_days=Decimal('0.50'))])):
            with self.assertRaises(ValueError):repository._daily(period,policy,rows,leaves)
        for key in ('paid_leave_treatment','unpaid_leave_treatment'):policy['leave_rules'][key]='BLOCK'
        with self.assertRaisesRegex(ValueError,'blocks'):repository._daily(period,policy,attendance,[leave])

    def test_no_production_callers_or_finalization_cutover(self):
        from pathlib import Path
        for name in ('app.py','payroll_workflow_repository.py','payroll_calculation_repository.py','payroll_entry_repository.py'):
            code=Path(name).read_text()
            self.assertNotIn('import payroll_evidence',code)
        import payroll_certification_repository as certs
        self.assertIsNone(certs.authoritative_evidence({},7))


if __name__=='__main__':unittest.main()
