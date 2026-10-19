import os
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch
from io import BytesIO

from openpyxl import Workbook, load_workbook
from finance_reporting import report, filters
from finance_export import generate_finance_report_excel, safe_text_cell


class FinanceReportingTests(unittest.TestCase):
    def records(self):
        base=dict(expense_number='EXP-TEST',expense_date=date(2026,1,1),category_id=1,
                  category_code='CAT',category_name='Category',department_name=None,supplier_name=None,
                  po_number=None,description='Description',reference_number=None,payment_method=None)
        return [dict(base,status=s,amount=Decimal(a)) for s,a in [('PAID','0.10'),('PAID','0.20'),('DRAFT','1.00'),('APPROVED','2.00'),('CANCELLED','3.00')]]

    def test_decimal_aggregates_include_all_states_but_only_paid_spending(self):
        with patch('finance_reporting.get_filtered_expenses',return_value=self.records()) as read:
            data=report(dict(year=2026,department_id=1,status=None,category_id=None,search_text='test'))
        read.assert_called_once()
        self.assertEqual(data['summary']['total_expenses'],5)
        self.assertEqual(data['summary']['total_amount'],Decimal('6.30'))
        self.assertEqual(data['summary']['paid_amount'],Decimal('0.30'))
        self.assertEqual(data['monthly_expenses'][0]['total_amount'],Decimal('0.30'))
        self.assertEqual(data['category_expenses'][0]['expense_count'],2)

    def test_empty_report_has_zero_counts_and_decimal_money(self):
        with patch('finance_reporting.get_filtered_expenses',return_value=[]):data=report({})
        self.assertEqual(data['summary']['paid_count'],0)
        self.assertEqual(data['summary']['paid_amount'],Decimal('0.00'))
        self.assertEqual(data['monthly_expenses'],[])

    def test_filter_normalization(self):
        selected=filters(dict(year='2025',status='paid',category_id='3',department_id='none',search=' Query '),2026)
        self.assertEqual(selected,dict(year=2025,status='PAID',category_id=3,department_id='none',search_text='Query'))
        self.assertEqual(filters(dict(year='999999999999',category_id='-1',department_id='NaN'),2026)['year'],2026)

    def test_workbook_roundtrip_dangerous_text_keeps_numeric_date_and_formatting(self):
        payloads=['=1+1','+SUM(A1:A2)','-1+1','@SUM(A1:A2)',' =1+1','\t=1+1','\r\n=1+1','\r=1+1','\n=1+1','\n\n=1+1',
                  '\ufeff=1+1','\u200b=1+1','\u00a0=1+1','\x00=1+1','\x0b@SUM(A1:A2)',
                  '=HYPERLINK("https://invalid.example","click")']
        for payload in payloads:
            with self.subTest(payload=repr(payload)):
                # Text serialization expands LF to platform newlines; XML normalizes CRLF/CR.
                expected = payload.replace('\n', os.linesep).replace('\r\n', '\n').replace('\r', '\n')
                row=self.records()[0]
                for key in ['expense_number','category_name','department_name','supplier_name','po_number','description','reference_number']:
                    row[key]=payload
                with patch('finance_reporting.get_filtered_expenses',return_value=[row]):data=report({})
                data['category_expenses'][0]['category_code']=payload
                wb=load_workbook(generate_finance_report_excel(2026,**{k:data[k] for k in ['summary','monthly_expenses','category_expenses','expense_records']}))
                self.assertEqual(wb.sheetnames,['Summary','Monthly Paid Expenses','Category Breakdown','Expense Records'])
                for column in [1,3,4,5,6,7,10]:
                    cell=wb['Expense Records'].cell(2,column)
                    self.assertEqual(cell.data_type,'s')
                    self.assertNotEqual(cell.data_type,'f')
                    if '\x00' not in payload and '\x0b' not in payload:
                        self.assertEqual(cell.value,expected)
                self.assertEqual(wb['Category Breakdown']['A2'].data_type,'s')
                self.assertEqual(wb['Category Breakdown']['B2'].data_type,'s')
                self.assertEqual(wb['Expense Records']['H2'].data_type,'n')
                self.assertEqual(wb['Expense Records']['H2'].value,0.1)
                self.assertEqual(wb['Expense Records']['B2'].data_type,'d')
                self.assertIn('0.00',wb['Expense Records']['H2'].number_format)
                self.assertFalse(any(c.data_type=='f' for ws in wb for row in ws for c in row))

    def test_helper_preserves_plain_values_and_does_not_touch_application_formulas(self):
        wb=Workbook();ws=wb.active
        for value in [Decimal('0.10'),date(2026,1,1),'Ordinary text']:
            self.assertEqual(safe_text_cell(ws,value),value)
        ws['A1']='=SUM(1,2)'  # Application-generated formulas are outside text sanitization.
        output=BytesIO();wb.save(output);output.seek(0)
        self.assertEqual(load_workbook(output).active['A1'].data_type,'f')
