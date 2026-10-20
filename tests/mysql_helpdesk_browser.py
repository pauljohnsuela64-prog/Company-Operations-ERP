"""Help Desk Chrome workflow composed with the existing isolated security runner."""
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import mysql_security_review as review


def main():
    original=subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_helpdesk_browser_') as folder:
        def browser(args,*positional,**kwargs):
            if not isinstance(args,list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args,*positional,**kwargs)
            import database
            with database.get_connection() as db:
                cur=db.cursor()
                cur.execute("INSERT INTO departments(department_code,department_name,is_active) VALUES('HELP-BROWSER','Historical Help Department',0)")
                department=cur.lastrowid
                cur.execute("INSERT INTO employees(employee_number,first_name,last_name,department_id,employment_status) VALUES('HELP-BROWSER','Browser','Help',%s,'Inactive')",(department,))
                employee=cur.lastrowid
                cur.execute("INSERT INTO helpdesk_categories(category_code,category_name,is_active) VALUES('HELP-BROWSER','Browser Help',1)")
                category=cur.lastrowid
                cur.execute("INSERT INTO helpdesk_categories(category_code,category_name,is_active) VALUES('HELP-OLD','Historical Help',0)")
                historical_category=cur.lastrowid
                cur.executemany("INSERT INTO helpdesk_tickets(ticket_number,employee_id,department_id,category_id,subject,description,priority,status,assigned_to,created_by,created_at) VALUES(%s,%s,%s,%s,'Historical','Historical fixture','HIGH','CANCELLED',5,1,'2020-01-01')",[(f'BROWSER-HISTORY-{i}',employee,department,historical_category) for i in range(61)])
                db.commit();cur.execute('SELECT * FROM helpdesk_tickets WHERE employee_id=%s ORDER BY ticket_id',(employee,));before=cur.fetchall()
            root=review.harness.ROOT
            source=(root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source=source.replace("require('./browser_it_authorization.cjs')",'require('+json.dumps(str(root/'tests/browser_it_authorization.cjs'))+')')
            marker="    console.log('SUCCESS: browser execution"
            assert source.count(marker)==1
            call='    await require('+json.dumps(str(root/'tests/browser_helpdesk.cjs'))+')({send,tab,evaluate,navigate,until,fixture:'+json.dumps(dict(employee=employee,category=category,historicalCategory=historical_category))+'});\n'
            source=source.replace(marker,call+marker)
            script=Path(folder)/'browser_helpdesk.cjs';script.write_text(source,encoding='utf-8')
            kwargs['timeout']=360
            result=original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode==0:
                with database.get_connection() as db:
                    cur=db.cursor()
                    cur.execute("SELECT * FROM helpdesk_tickets WHERE employee_id=%s AND ticket_number LIKE 'BROWSER-HISTORY-%%' ORDER BY ticket_id",(employee,));assert cur.fetchall()==before
                    cur.execute("SELECT ticket_id,status,assigned_to,resolution,department_id FROM helpdesk_tickets WHERE employee_id=%s AND ticket_number NOT LIKE 'BROWSER-HISTORY-%%'",(employee,));rows=cur.fetchall()
                    assert len(rows)==1 and rows[0][1:]==('CLOSED',6,'PRIVATE resolution',department),rows
                    identity=rows[0][0]
                    cur.execute('SELECT action_type FROM helpdesk_ticket_history WHERE ticket_id=%s ORDER BY history_id',(identity,));assert cur.fetchall()==[('CREATED',),('ASSIGNED',),('STATUS_CHANGE',),('RESOLVED',),('STATUS_CHANGE',)]
                    cur.execute("SELECT action,description FROM audit_logs WHERE module='HELP_DESK' AND entity_id=%s ORDER BY audit_log_id",(str(identity),));events=cur.fetchall()
                    assert [event[0] for event in events]==['CREATE','ASSIGN','START','RESOLVE','CLOSE'],events
                    assert all('PRIVATE' not in event[1] and 'description' not in event[1] for event in events)
                print('PASS Chrome Help Desk persisted closed ticket, atomic history and five safe business audits; invalid/viewer writes blocked and old history retained')
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run=review.run
            review.harness.main()


if __name__=='__main__':main()
