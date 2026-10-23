"""Remaining-module real-browser checks on the existing verified disposable security server.

Supply ERP_GUI_BOOTSTRAP_CSS (existing 5.3.8 asset) and ERP_GUI_SCREENSHOTS.
No configured/company database or external browser resource is used.
"""
import re
import argparse
import sys
import base64
from gui_contracts import watch_contracts
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import mysql_security_review as review


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['stock','finance','hr','it','admin','all'])
    args_phase = parser.parse_args().phase
    sys.argv = [sys.argv[0]]
    vendor = Path(os.environ['ERP_GUI_BOOTSTRAP_CSS']).read_text(encoding='utf-8')
    assert 'Bootstrap v5.3.8' in ' '.join(vendor.split())
    artifacts = Path(os.environ['ERP_GUI_SCREENSHOTS']).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    original = subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_gui_v1_') as folder:
        def browser(args, *positional, **kwargs):
            if not isinstance(args, list) or not any(str(a).endswith('browser_security_review.cjs') for a in args):
                return original(args, *positional, **kwargs)
            import database
            import app as erp
            from flask import request


            with database.get_connection() as db:
                cur = db.cursor()
                # The base security harness does not visit entry/payslip screens.
                # Load their existing schema only on this verified disposable DB.
                source = (review.harness.ROOT/'database/payroll_adjustments_schema.sql').read_text()
                for statement in re.sub(r'--[^\n]*', '', source).split(';'):
                    if statement.strip() and not re.match(r'\s*USE\b', statement, re.I):
                        cur.execute(statement)
                # Synthetic reader fixture only; production grants are untouched.
                cur.execute("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code IN ('inventory.view','finance.view','employees.view','departments.view','attendance.view','leave.view','payroll.view','it_assets.view','helpdesk.view','audit_logs.view')")
                cur.execute("INSERT INTO inventory_items(item_id,item_code,item_name,unit_of_measure) VALUES(990,'GUI-LONG',%s,'pcs')", ('<script>long</script>'+'I'*120,))
                cur.execute("INSERT INTO warehouses(warehouse_id,warehouse_code,warehouse_name,location) VALUES(990,'GUI-WH',%s,%s)", ('W'*100,'L'*255))
                cur.execute('INSERT INTO inventory_stock(item_id,warehouse_id,quantity) VALUES(990,990,12.34)')
                cur.execute("INSERT INTO departments(department_id,department_code,department_name) VALUES(990,'GUI-DEPT',%s)", ('Finance department '+'D'*80,))
                cur.execute("INSERT INTO expense_categories(category_id,category_code,category_name) VALUES(990,'GUI-CAT','GUI Expenses')")
                cur.execute("INSERT INTO expenses(expense_id,expense_number,expense_date,category_id,department_id,description,amount,status,created_by) VALUES(990,'GUI-EXPENSE','2026-10-01',990,990,%s,1234.56,'DRAFT',1)", ('<img src=x>'+'E'*200,))
                cur.execute("INSERT INTO department_budgets(budget_id,department_id,budget_year,budget_amount,created_by) VALUES(990,990,2026,10000.00,1)")
                cur.execute("INSERT INTO employees(employee_id,employee_number,first_name,last_name,department_id) VALUES(990,'GUI-EMP',%s,'Employee',990)", ('Long'+'N'*70,))
                cur.execute("INSERT INTO attendance_records(attendance_id,employee_id,attendance_date,status,created_by) VALUES(990,990,'2026-10-01','PRESENT',1)")
                cur.execute("INSERT INTO leave_types(leave_type_id,leave_code,leave_name,annual_entitlement,is_paid,is_active) VALUES(990,'GUI-LEAVE','GUI Leave',15,1,1)")
                cur.execute("INSERT INTO leave_requests(leave_request_id,request_number,employee_id,leave_type_id,start_date,end_date,total_days,reason,status,requested_by) VALUES(990,'GUI-REQUEST',990,990,'2026-11-01','2026-11-01',1,%s,'PENDING',1)", ('Reason '+'R'*200,))
                cur.execute("INSERT INTO employee_compensation(compensation_id,employee_id,pay_type,basic_rate,effective_date,created_by) VALUES(990,990,'MONTHLY',12345.67,'2026-01-01',1)")
                cur.execute("INSERT INTO payroll_periods(payroll_period_id,period_number,period_name,start_date,end_date,pay_date,created_by) VALUES(990,'GUI-PERIOD','GUI Payroll period','2026-10-01','2026-10-31','2026-11-01',1)")
                cur.execute("INSERT INTO payroll_entries(payroll_entry_id,payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,generated_by) VALUES(990,990,990,990,'MONTHLY',12345.67,1)")
                cur.execute("INSERT INTO payroll_periods(payroll_period_id,period_number,period_name,start_date,end_date,pay_date,status,created_by) VALUES(991,'GUI-PAID','Paid GUI Payroll','2026-09-01','2026-09-30','2026-10-01','PAID',1)")
                cur.execute("INSERT INTO payroll_entries(payroll_entry_id,payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,generated_by) VALUES(991,991,990,990,'MONTHLY',12345.67,1)")
                cur.execute("INSERT INTO roles(role_id,role_name) VALUES(990,'GUI approver')")
                cur.execute("INSERT INTO users(user_id,role_id,username,password_hash) SELECT 990,990,'gui-approver',password_hash FROM users WHERE user_id=1")
                cur.execute("INSERT INTO role_permissions SELECT 990,permission_id FROM permissions WHERE permission_code IN ('finance.view','finance.expenses.approve','leave.view','leave.approve','payroll.view','payroll.approve')")
                db.commit()
                snapshots = {}
                for table in ('inventory_stock','stock_movements','purchase_orders','employees','departments','attendance_records','leave_requests','leave_types','employee_compensation','payroll_periods','payroll_entries','payroll_adjustments','expenses','department_budgets'):
                    cur.execute(f'SELECT * FROM {table} ORDER BY 1,2')
                    snapshots[table] = cur.fetchall()
            root = review.harness.ROOT
            source = (root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source = source.replace("    await require('./browser_it_authorization.cjs')({base, controlKey, send, tab, evaluate, navigate, until});", '')
            source = 'const GUI_ERRORS=[],GUI_DIALOGS=[];let GUI_CONFIRM=true;const GUI_BOOTSTRAP='+json.dumps(base64.b64encode(vendor.encode()).decode())+';\n'+source
            marker = '    if (!message.id) return;'
            assert source.count(marker) == 1
            source = source.replace(marker, """    if(message.method==='Fetch.requestPaused') {
      const p=message.params;
      if(p.request.url==='https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css') send('Fetch.fulfillRequest',{requestId:p.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/css'}],body:GUI_BOOTSTRAP},message.sessionId).catch(console.error);
      else send('Fetch.failRequest',{requestId:p.requestId,errorReason:'BlockedByClient'},message.sessionId).catch(console.error);
      return;
    }
    if(message.method==='Page.javascriptDialogOpening') {GUI_DIALOGS.push(message.params.message);send('Page.handleJavaScriptDialog',{accept:GUI_CONFIRM},message.sessionId).catch(console.error);}
    if(message.method==='Runtime.exceptionThrown') GUI_ERRORS.push(message.params.exceptionDetails.text);
    if(message.method==='Runtime.consoleAPICalled' && message.params.type==='error') GUI_ERRORS.push('console.error');
"""+marker)
            source = source.replace("await send('Network.setBlockedURLs', {urls:['https://*']}, sessionId);", "await send('Fetch.enable',{patterns:[{urlPattern:'https://*'}]},sessionId);\n    await send('Runtime.enable',{},sessionId);")
            marker = "    console.log('SUCCESS: browser execution"
            assert source.count(marker) == 1
            additions = '    await require('+json.dumps(str(root/'tests/browser_gui_v1.cjs'))+')({send,tab,evaluate,navigate,until,errors:GUI_ERRORS,phase:'+json.dumps(args_phase)+',artifacts:'+json.dumps(str(artifacts))+'});\n'
            source = source.replace(marker, additions+marker)
            script = Path(folder)/'gui_v1_security.cjs'
            script.write_text(source,encoding='utf-8')
            kwargs['timeout'] = 900
            with watch_contracts(['inventory/stock/','finance/','employees/','departments/','attendance/','leave/','payroll/','it_assets/','help_desk/','admin/','security/','login.html']) as checked:
                result = original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode == 0:
                assert checked, 'No baseline contracts checked'
                with database.get_connection() as db:
                    cur = db.cursor()
                    for table, expected in snapshots.items():
                        cur.execute(f'SELECT * FROM {table} ORDER BY 1,2')
                        assert cur.fetchall() == expected, f'Unexpected visual-suite mutation: {table}'
                print('PASS GUI baseline form/link/script contracts:', ', '.join(sorted(checked)))
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run = review.run
            review.harness.main()


if __name__ == '__main__':
    main()
