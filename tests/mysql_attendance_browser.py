"""Attendance Chrome workflow composed with the existing isolated security runner."""
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import mysql_security_review as review


def main():
    original=subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_attendance_browser_') as folder:
        def browser(args,*positional,**kwargs):
            if not isinstance(args,list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args,*positional,**kwargs)
            import database
            with database.get_connection() as db:
                cur=db.cursor()
                cur.execute("INSERT INTO departments(department_code,department_name,is_active) VALUES('ATT-BROWSER','Historical Attendance Department',0)")
                department=cur.lastrowid
                cur.execute("INSERT INTO employees(employee_number,first_name,last_name,department_id) VALUES('ATT-BROWSER','Browser','Attendance',%s)",(department,))
                employee=cur.lastrowid
                cur.execute("INSERT INTO roles(role_id,role_name) VALUES(7,'Attendance Browser Viewer')")
                cur.execute("INSERT INTO role_permissions SELECT 7,permission_id FROM permissions WHERE permission_code IN ('attendance.view','dashboard.view')")
                cur.execute("INSERT INTO users(role_id,username,password_hash) SELECT 7,'attendance-viewer',password_hash FROM users WHERE user_id=1")
                cur.executemany("INSERT INTO attendance_records(employee_id,attendance_date,status,notes,created_by) VALUES(%s,%s,'PRESENT','Historical fixture',1)",[(employee,date(2023,1,1)+timedelta(days=i)) for i in range(61)])
                db.commit();cur.execute('SELECT * FROM attendance_records WHERE employee_id=%s ORDER BY attendance_id',(employee,));before=cur.fetchall()
            root=review.harness.ROOT
            source=(root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source=source.replace("require('./browser_it_authorization.cjs')",'require('+json.dumps(str(root/'tests/browser_it_authorization.cjs'))+')')
            marker="    console.log('SUCCESS: browser execution"
            assert source.count(marker)==1
            call='    await require('+json.dumps(str(root/'tests/browser_attendance.cjs'))+')({send,tab,evaluate,navigate,until,fixture:'+json.dumps(dict(employee=employee,department=department))+'});\n'
            source=source.replace(marker,call+marker)
            script=Path(folder)/'browser_attendance.cjs';script.write_text(source,encoding='utf-8')
            kwargs['timeout']=360
            result=original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode==0:
                with database.get_connection() as db:
                    cur=db.cursor()
                    cur.execute("SELECT * FROM attendance_records WHERE employee_id=%s AND attendance_date<'2024-01-01' ORDER BY attendance_id",(employee,));assert cur.fetchall()==before
                    cur.execute("SELECT status,time_in,time_out FROM attendance_records WHERE employee_id=%s AND attendance_date='2026-03-01'",(employee,));assert cur.fetchall()==[('HALF_DAY',timedelta(hours=23,minutes=59,seconds=59),timedelta())]
                    cur.execute("SELECT COUNT(*) FROM attendance_records WHERE employee_id=%s AND attendance_date='2026-03-02'",(employee,));assert cur.fetchall()==[(0,)]
                    cur.execute("SELECT action,description FROM audit_logs WHERE module='ATTENDANCE' ORDER BY audit_log_id");events=cur.fetchall()
                    assert [row[0] for row in events]==['CREATE','UPDATE'],events
                    assert all('PRIVATE' not in row[1] and 'notes' not in row[1] for row in events)
                print('PASS Chrome Attendance persisted records/audits, confidential-note exclusion, old history preserved and zero unauthorized writes')
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run=review.run
            review.harness.main()


if __name__=='__main__':main()
