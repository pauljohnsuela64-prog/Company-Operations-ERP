"""Read-only repository boundaries and pure structural validation, no company DB."""
from datetime import date,datetime
import unittest
from unittest.mock import MagicMock,patch

from mysql.connector import Error
import hr_lifecycle_repository as repo
from hr_lifecycle_validation import (validate_proposal,json_object,LifecycleInputError,
                                     BIGINT_MAX,positive_integer)


def proposal(**changes):
    result=dict(schema_version=1,employee_id=1,expected_employee_revision=17,
                event_type='HIRE',effective_date=date(2024,1,1),effective_order=1,
                source={'type':'DOCUMENT','reference':'synthetic-only'},
                reason='Synthetic structural test',submitted_by=1,changes={})
    result.update(changes)
    return result


class StructureTests(unittest.TestCase):
    def test_valid_types_and_detached_explicit_clear(self):
        raw=proposal(changes={'department_id':{'op':'clear'},'job_title':{'op':'set','value':'Engineer'},
                              'verified_start_date':{'op':'set','value':date(2024,1,1)}})
        result=validate_proposal(raw)
        self.assertEqual(result['changes']['department_id'],{'op':'clear'})
        self.assertEqual(result['changes']['verified_start_date']['value'],'2024-01-01')
        self.assertNotIn('employment_status',result['changes'])
        result['source']['reference']='Changed';self.assertEqual(raw['source']['reference'],'synthetic-only')

    def test_no_policy_approval_or_reference_lookup(self):
        # Structurally valid IDs/text do not assert existence or approved transitions.
        self.assertEqual(validate_proposal(proposal(employee_id=999,changes={
            'employment_status':{'op':'set','value':'Not a policy-approved status'}}))['employee_id'],999)
        validate_proposal(proposal(event_type='CORRECT',supersedes_event_id=BIGINT_MAX))
        validate_proposal(proposal(event_type='VOID',supersedes_event_id=1))

    def test_exact_structural_boundaries(self):
        raw=proposal(employee_id=2147483647,submitted_by=2147483647,
                     expected_employee_revision=BIGINT_MAX,effective_order=2147483647,
                     effective_date=date(1000,1,1),employment_period_id=BIGINT_MAX,
                     source={'type':'x'*30,'reference':'x'*255,'version':'x'*50},reason='x'*255,
                     changes={'job_title':{'op':'set','value':'x'*100},
                              'employment_status':{'op':'set','value':'x'*30},
                              'department_id':{'op':'set','value':2147483647},
                              'end_exclusive_date':{'op':'set','value':date(9999,12,31)}})
        self.assertEqual(validate_proposal(raw)['changes']['end_exclusive_date']['value'],'9999-12-31')
        self.assertEqual(len(json_object({'x':'x'*16375})['x']),16375)
        with self.assertRaises(LifecycleInputError):json_object({'x':'x'*16376})
        self.assertEqual(len(json_object({'x':'é'*8187})['x']),8187)
        with self.assertRaises(LifecycleInputError):json_object({'x':'é'*8188})

    def test_invalid_envelopes(self):
        invalid=[dict(schema_version=True),dict(schema_version=2),dict(employee_id=True),
                 dict(employee_id=0),dict(employee_id=2147483648),dict(submitted_by='1'),
                 dict(expected_employee_revision=0),dict(expected_employee_revision=BIGINT_MAX+1),
                 dict(effective_order=0),dict(effective_date='2024-01-01'),
                 dict(effective_date=datetime(2024,1,1)),dict(effective_date=date(999,1,1)),
                 dict(event_type='UNKNOWN'),dict(event_type=[]),dict(supersedes_event_id=1),
                 dict(event_type='CORRECT'),dict(employment_period_id=-1),dict(reason=''),
                 dict(reason='x'*256),dict(reason='\ud800'),dict(source={}),
                 dict(source={'type':'D','reference':''}),dict(source={'type':'x'*31,'reference':'S'}),
                 dict(source={'type':'D','reference':'x'*256}),
                 dict(source={'type':'D','reference':'S','version':'x'*51}),dict(unsupported=1)]
        for change in invalid:
            with self.subTest(change=str(change)[:60]),self.assertRaises(LifecycleInputError):validate_proposal(proposal(**change))
        raw=proposal();del raw['source']
        with self.assertRaises(LifecycleInputError):validate_proposal(raw)

    def test_invalid_change_structure(self):
        for changes in ([],{'job_title':None},{'job_title':{'op':'set','value':None}},
                        {'job_title':{'op':'clear','value':None}},{'job_title':{'op':'unchanged'}},
                        {'job_title':{'op':'set','value':'x'*101}}, {'secret':{'op':'clear'}},
                        {'department_id':{'op':'set','value':True}},
                        {'end_exclusive_date':{'op':'set','value':'2024-01-01'}}):
            with self.subTest(changes=changes),self.assertRaises(LifecycleInputError):
                validate_proposal(proposal(changes=changes))

    def test_json_bounds_and_unsupported_values(self):
        for invalid in ([],{1:'bad'},{'x':float('nan')},{'x':float('inf')},{'x':date.today()},
                        {'x':BIGINT_MAX+1},{'x':'x'*16384},{'x':'\ud800'}):
            with self.assertRaises(LifecycleInputError):json_object(invalid)
        cycle={};cycle['self']=cycle
        with self.assertRaises(LifecycleInputError):json_object(cycle)
        self.assertEqual(json_object({'text':'普通','nullable':None,'number':1.5}),
                         {'text':'普通','nullable':None,'number':1.5})
        for bad in (False,True,0,-1,1.0,'1',BIGINT_MAX+1):
            with self.assertRaises(LifecycleInputError):positive_integer(bad,'ID')


class ReaderTests(unittest.TestCase):
    def test_invalid_scope_and_pagination_never_connect(self):
        with patch.object(repo,'get_connection',side_effect=AssertionError('No DB')):
            for value in (True,0,-1,'1',2147483648):
                with self.assertRaises(LifecycleInputError):repo.get_lifecycle_status(value)
            for kwargs in ({'limit':0},{'limit':101},{'offset':-1},{'offset':100001},{'offset':True}):
                with self.assertRaises(LifecycleInputError):repo.list_employment_events(1,**kwargs)
            with self.assertRaises(LifecycleInputError):repo.get_employment_event(1,0)
            with self.assertRaises(LifecycleInputError):repo.get_lifecycle_request(1,'1')
            with self.assertRaises(LifecycleInputError):repo.get_history_coverage(1,date(2024,1,1),date(2024,1,1))

    def test_only_parameterized_selects_and_read_only_snapshot(self):
        db=MagicMock();cur=db.cursor.return_value;cur.fetchone.return_value=None;cur.fetchall.return_value=[]
        with patch.object(repo,'get_connection',return_value=db):
            for action in (lambda:repo.get_lifecycle_status(1),lambda:repo.list_employment_periods(1),
                           lambda:repo.list_employment_events(1),lambda:repo.get_employment_event(1,2),
                           lambda:repo.list_lifecycle_requests(1),lambda:repo.get_lifecycle_request(1,2),
                           lambda:repo.get_correction_relationships(1,2),
                           lambda:repo.get_history_coverage(1,date(2024,1,1),date(2025,1,1))):action()
        for call in cur.execute.call_args_list:
            self.assertTrue(call.args[0].lstrip().startswith('SELECT'))
            self.assertIn('%s',call.args[0]);self.assertEqual(call.args[1][0],1)
        db.commit.assert_not_called()
        db.start_transaction.assert_called_with(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        self.assertEqual(db.rollback.call_count,8);self.assertEqual(db.close.call_count,8)

    def test_storage_and_configuration_errors_do_not_disclose_details(self):
        for failure in (Error('secret SQL employee source'),ValueError('secret configuration')):
            with patch.object(repo,'get_connection',side_effect=failure),self.assertRaises(repo.LifecycleReadError) as caught:
                repo.get_lifecycle_status(1)
            self.assertNotIn('secret',str(caught.exception))
        for step in ('execute','close'):
            db=MagicMock();getattr(db.cursor.return_value,step).side_effect=Error('secret SQL')
            with patch.object(repo,'get_connection',return_value=db),self.assertRaises(repo.LifecycleReadError) as caught:
                repo.get_lifecycle_status(1)
            self.assertNotIn('secret',str(caught.exception));db.close.assert_called_once()
        for step in ('start_transaction','rollback','close'):
            db=MagicMock();getattr(db,step).side_effect=Error('secret connection details')
            with patch.object(repo,'get_connection',return_value=db),self.assertRaises(repo.LifecycleReadError) as caught:
                repo.get_lifecycle_status(1)
            self.assertNotIn('secret',str(caught.exception));db.close.assert_called_once()


if __name__=='__main__':unittest.main()
