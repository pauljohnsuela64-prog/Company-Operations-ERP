"""Offline transaction-boundary, historical projection and isolation checks."""
import ast
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

import payroll_certification_repository as certs
import payroll_evidence_repository as evidence


class PeriodAtomicityTests(unittest.TestCase):
    def test_cursor_primitives_require_active_transaction(self):
        for auto,active in ((False,False),(True,False)):
            cursor=Mock();cursor._connection.autocommit=auto;cursor._connection.in_transaction=active
            for operation in (lambda:evidence.persist_proposed_in_transaction(cursor,1,1,{},7),
                              lambda:evidence.invalidate_period_in_transaction(cursor,1)):
                with self.assertRaisesRegex(ValueError,'caller-owned'):operation()
            cursor.execute.assert_not_called()

    def test_cursor_primitive_propagates_without_transaction_ownership(self):
        cursor=Mock();cursor._connection.autocommit=False;cursor._connection.in_transaction=True
        with patch.object(evidence,'get_connection') as connection,patch.object(evidence,'validate_eligibility',side_effect=ValueError('source invalid')):
            with self.assertRaisesRegex(ValueError,'source invalid'):
                evidence.persist_proposed_in_transaction(cursor,1,1,{},7)
            connection.assert_not_called()
            cursor._connection.commit.assert_not_called();cursor._connection.rollback.assert_not_called()

    def test_public_helper_retains_connection_commit_and_rollback_contract(self):
        for failure in (False,True):
            connection=Mock();cursor=connection.cursor.return_value
            with patch.object(evidence,'get_connection',return_value=connection) as factory,patch.object(
                    evidence,'persist_proposed_in_transaction',side_effect=ValueError('rejected') if failure else None,
                    return_value=42) as primitive:
                if failure:
                    with self.assertRaisesRegex(ValueError,'rejected'):evidence.persist_proposed(1,2,{},7)
                    connection.rollback.assert_called_once();connection.commit.assert_not_called()
                else:
                    self.assertEqual(evidence.persist_proposed(1,2,{},7),42)
                    connection.commit.assert_called_once();connection.rollback.assert_not_called()
                factory.assert_called_once();connection.start_transaction.assert_called_once()
                primitive.assert_called_once_with(cursor,1,2,{},7)
                cursor.close.assert_called_once();connection.close.assert_called_once()

    def test_known_certification_projections_without_resealing(self):
        period=dict(payroll_period_id=1,policy_version_id=2,cutoff_code='A',start_date=date(2035,1,1),end_date=date(2035,1,15))
        base=dict(certification_id=3,evidence_format_version=1,revision=1,state='ASSEMBLY',
                  certified_by=None,certified_at=None,certification_digest=None,members=[],events=[])
        # Exact original projection independently expressed as it existed pre-007.
        old=certs.digest(dict(period=period,header={k:v for k,v in base.items() if k not in
            ('members','events','certification_digest','state','certified_by','certified_at')},members=[]))
        row=dict(base,correction_reason=None,correction_reference=None,state='SEALED',certification_digest=old)
        before=dict(row);new=certs._publication_digest(period,row)
        self.assertNotEqual(old,new)
        self.assertEqual(certs.verify_publication_digest(period,dict(base,state='SEALED',certification_digest=old),old),'006')
        self.assertEqual(certs.verify_publication_digest(period,row,new),'006')
        self.assertEqual(row,before)
        self.assertEqual(certs.verify_publication_digest(period,dict(row,certification_digest=new),new),'007')
        for changed in (dict(row,revision=2),dict(row,correction_reason='SYNTHETIC:changed'),
                        dict(row,correction_reference='SYNTHETIC:changed'),dict(row,certification_digest='0'*64),
                        dict(row,evidence_format_version=2),dict(row,evidence_format_version=True)):
            with self.assertRaises(ValueError):
                certs.verify_publication_digest(period,changed,certs._publication_digest(period,changed))

    def test_no_production_adapter_callers_and_no_hidden_commit_in_primitives(self):
        root=Path(__file__).resolve().parents[1]
        for path in root.glob('*.py'):
            self.assertNotIn('payroll_synthetic_period',path.read_text(encoding='utf-8-sig'),path.name)
        tree=ast.parse((root/'payroll_evidence_repository.py').read_text())
        for function in tree.body:
            if isinstance(function,ast.FunctionDef) and function.name in ('persist_proposed_in_transaction','invalidate_period_in_transaction'):
                for call in ast.walk(function):
                    if isinstance(call,ast.Call):
                        self.assertNotIn(getattr(call.func,'attr',''),('commit','rollback','cursor'))
                        self.assertNotEqual(getattr(call.func,'id',''),'get_connection')
        import payroll_certification_repository as production
        self.assertIsNone(production.authoritative_evidence({},7))


if __name__=='__main__':unittest.main()
