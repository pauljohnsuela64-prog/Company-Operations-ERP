"""Synthetic IT reporting/export regressions; never connect to company databases."""
import os
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from io import BytesIO
import importlib
import unittest
from unittest.mock import patch, MagicMock
from openpyxl import load_workbook
from it_asset_export import generate_it_asset_report_excel
from security_helpers import csrf_client, stamp_session, user_state


def report_fixture(text='Asset'):
    counts=dict(total_assets=1,available_count=1,assigned_count=0,maintenance_count=0,retired_count=0,lost_count=0)
    asset={key:text for key in ['asset_tag','asset_name','category_name','brand','model','serial_number','department_name','assigned_employee_name','notes']}
    asset.update(asset_id=1,status='AVAILABLE',condition_status='DAMAGED',purchase_cost=Decimal('0.10'),purchase_date=date(2026,1,2),warranty_expiry=date(2027,1,2))
    return dict(summary=counts,category_summary=[dict(counts,category_code=text,category_name=text,total_purchase_cost=Decimal('0.10'))],
                department_summary=[dict(counts,department_name=text,total_purchase_cost=Decimal('0.10'))],assets=[asset])


class AssetExportTests(unittest.TestCase):
    def test_xlsx_payloads_are_strings_in_every_user_text_column(self):
        for payload in ['=1+1','+SUM(A1:A2)','-1+2','@SUM(A1:A2)','\r=1+1','\n=1+1','\n\n=1+1',' \t\r\n=HYPERLINK("https://invalid.example")','\ufeff\u200b=1','\u00a0=1','\x00=1','\x0b+1','\ud800=1','\uffff=1','#N/A','Ordinary text']:
            with self.subTest(payload=repr(payload)):
                # Text serialization expands LF to platform newlines; XML normalizes CRLF/CR.
                expected = payload.replace('\n', os.linesep).replace('\r\n', '\n').replace('\r', '\n')
                wb=load_workbook(generate_it_asset_report_excel(**report_fixture(payload)),data_only=False)
                self.assertEqual(wb.sheetnames,['Summary','By Category','By Department','Asset Register'])
                for name,columns in [('By Category',[1,2]),('By Department',[1]),('Asset Register',[1,2,3,4,5,6,7,8,14])]:
                    for column in columns:
                        cell=wb[name].cell(2,column)
                        self.assertEqual(cell.data_type,'s')
                        self.assertTrue(cell.value)
                        if not any(c in payload for c in ['\x00','\x0b','\ud800','\uffff']):self.assertEqual(cell.value,expected)
                self.assertEqual(wb['Asset Register']['L2'].data_type,'n')
                self.assertEqual(wb['Asset Register']['L2'].value,0.1)
                self.assertEqual(wb['Asset Register']['K2'].data_type,'d')
                self.assertEqual(wb['Asset Register']['K2'].value.date(),date(2026,1,2))
                self.assertEqual(wb['Asset Register'].freeze_panes,'A2')
                self.assertEqual(wb['Asset Register'].auto_filter.ref,'A1:N2')
                self.assertFalse(any(c.data_type=='f' for s in wb for row in s for c in row))

    def test_empty_report_retains_structure(self):
        report=report_fixture();report.update(assets=[],category_summary=[],department_summary=[])
        wb=load_workbook(generate_it_asset_report_excel(**report))
        self.assertEqual(wb['Asset Register'].max_row,1)


class AssetReportRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-report',ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("database.ensure_ready"))  # Mock schema boundary for route unit tests.
        self.state=user_state(permissions=['it_assets.view'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.report=self.stack.enter_context(patch.object(self.erp,'get_it_asset_report_data',return_value=dict(report_fixture(),diagnostics=[])))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as sess:stamp_session(self.erp.app,sess,self.state)

    def test_export_viewer_response_and_fresh_denials(self):
        response=self.client.get('/it/assets/reports/export')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'private, no-store')
        self.assertIn('attachment;',response.headers['Content-Disposition'])
        self.assertIn('IT_Asset_Report.xlsx',response.headers['Content-Disposition'])
        self.assertEqual(response.mimetype,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertEqual(load_workbook(BytesIO(response.data))['Asset Register']['A2'].value,'Asset')
        self.state['permissions']=[]
        self.report.reset_mock()
        for path in ['/it/assets/reports','/it/assets/reports/export']:
            self.assertEqual(self.client.get(path).status_code,302)
        self.report.assert_not_called();self.audit.assert_not_called()

    def test_snapshot_failure_rolls_back_and_closes(self):
        repo=importlib.import_module('it_asset_repository');connection=MagicMock()
        with patch.object(repo,'get_connection',return_value=connection),patch.object(repo,'get_it_asset_summary',side_effect=RuntimeError('read failed')):
            with self.assertRaises(RuntimeError):repo.get_it_asset_report_data()
        connection.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ',consistent_snapshot=True,readonly=True)
        connection.rollback.assert_called_once();connection.close.assert_called_once();connection.commit.assert_not_called()


    def test_diagnostics_separate_valid_custody_from_inconsistent_history(self):
        repo=importlib.import_module('it_asset_repository');connection=MagicMock()
        cursor=connection.cursor.return_value
        def row(aid,status,employee,active,history,maintenance):
            return dict(asset_id=aid,asset_tag=str(aid),status=status,assigned_employee_id=employee,
                        active_count=active,history_employee_id=history,open_count=maintenance)
        cursor.fetchall.return_value=[row(1,'LOST',1,1,1,0),row(2,'MAINTENANCE',1,1,1,1),
            row(3,'ASSIGNED',1,1,2,0),row(4,'ASSIGNED',None,0,None,0),
            row(5,'AVAILABLE',1,1,1,0),row(6,'MAINTENANCE',None,0,None,0)]
        with ExitStack() as stack:
            stack.enter_context(patch.object(repo,'get_connection',return_value=connection))
            for name in ['get_it_asset_summary','get_it_asset_report_by_category','get_it_asset_report_by_department','get_filtered_it_assets']:
                stack.enter_context(patch.object(repo,name,return_value=[]))
            data=repo.get_it_asset_report_data()
        self.assertEqual([r['asset_id'] for r in data['diagnostics']],[3,4,5,6])
        self.assertIn('employee differs',data['diagnostics'][0]['issues'][0])
        connection.commit.assert_called_once();connection.close.assert_called_once()
