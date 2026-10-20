"""Leave Chrome workflow composed with the existing isolated security runner."""
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import mysql_security_review as review


def main():
    original=subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_leave_browser_') as folder:
        def browser(args,*positional,**kwargs):
            if not isinstance(args,list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args,*positional,**kwargs)
            import database
            with database.get_connection() as db:
                cur=db.cursor()
                cur.execute("INSERT INTO departments(department_code,department_name,is_active) VALUES('LEAVE-BROWSER','Historical Leave Department',0)")
                department=cur.lastrowid
                cur.execute("INSERT INTO employees(employee_number,first_name,last_name,department_id) VALUES('LEAVE-BROWSER','Browser','Leave',%s)",(department,))
                employee=cur.lastrowid
                cur.execute("INSERT INTO leave_types(leave_code,leave_name,annual_entitlement,is_paid,is_active) VALUES('LEAVE-BROWSER','Browser Leave',NULL,1,1)")
                leave_type=cur.lastrowid
                cur.execute("INSERT INTO roles(role_id,role_name) VALUES(7,'Leave Browser Viewer')")
                cur.execute("INSERT INTO role_permissions SELECT 7,permission_id FROM permissions WHERE permission_code IN ('leave.view','dashboard.view')")
                cur.execute("INSERT INTO users(role_id,username,password_hash) SELECT 7,'leave-viewer',password_hash FROM users WHERE user_id=1")
                cur.executemany("INSERT INTO leave_requests(request_number,employee_id,leave_type_id,start_date,end_date,total_days,reason,status,requested_by) VALUES(%s,%s,%s,%s,%s,1,'Historical fixture','REJECTED',1)",[(f'BROWSER-HISTORY-{i}',employee,leave_type,date(2023,1,1)+timedelta(days=i),date(2023,1,1)+timedelta(days=i)) for i in range(61)])
                db.commit();cur.execute('SELECT * FROM leave_requests WHERE employee_id=%s ORDER BY leave_request_id',(employee,));before=cur.fetchall()
            root=review.harness.ROOT
            source=(root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source=source.replace("require('./browser_it_authorization.cjs')",'require('+json.dumps(str(root/'tests/browser_it_authorization.cjs'))+')')
            marker="    console.log('SUCCESS: browser execution"
            assert source.count(marker)==1
            call='    await require('+json.dumps(str(root/'tests/browser_leave.cjs'))+')({send,tab,evaluate,navigate,until,fixture:'+json.dumps(dict(employee=employee,department=department,type=leave_type))+'});\n'
            source=source.replace(marker,call+marker)
            script=Path(folder)/'browser_leave.cjs';script.write_text(source,encoding='utf-8')
            kwargs['timeout']=360
            result=original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode==0:
                with database.get_connection() as db:
                    cur=db.cursor()
                    cur.execute("SELECT * FROM leave_requests WHERE employee_id=%s AND start_date<'2024-01-01' ORDER BY leave_request_id",(employee,));assert cur.fetchall()==before
                    cur.execute("SELECT start_date,status FROM leave_requests WHERE employee_id=%s AND start_date>'2030-01-01' ORDER BY start_date",(employee,));assert cur.fetchall()==[(date(2035,1,1),'APPROVED'),(date(2035,2,1),'REJECTED'),(date(2035,3,1),'CANCELLED')]
                    cur.execute("SELECT attendance_date,status FROM attendance_records WHERE employee_id=%s ORDER BY attendance_date",(employee,));assert cur.fetchall()==[(date(2035,1,1),'ON_LEAVE'),(date(2035,1,2),'ON_LEAVE')]
                    cur.execute("SELECT action,description FROM audit_logs WHERE module='LEAVE' ORDER BY audit_log_id");events=cur.fetchall()
                    assert [row[0] for row in events]==['APPROVE','REJECT','CANCEL'],events
                    assert all('PRIVATE' not in row[1] and 'reason' not in row[1] for row in events)
                print('PASS Chrome Leave persisted workflow/Attendance/audits, confidential-reason exclusion, history preserved and unauthorized writes blocked')
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run=review.run
            review.harness.main()


if __name__=='__main__':main()
