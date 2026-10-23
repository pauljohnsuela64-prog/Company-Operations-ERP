"""Real freshness forms and security roles, composed with verified disposable runner."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
from unittest.mock import patch
from datetime import date, timedelta
import mysql_security_review as review


def main():
    original = subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_freshness_browser_') as folder:
        def browser(args,*positional,**kwargs):
            if not isinstance(args,list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args,*positional,**kwargs)
            import database
            import app as erp
            def sql(query,params=(),fetch=False):
                with database.get_connection() as db:
                    cur=db.cursor();cur.execute(query,params)
                    result=cur.fetchall() if fetch else cur.lastrowid
                    db.commit();return result
            with database.get_connection() as db:
                cur=db.cursor()
                source=(review.harness.ROOT/'database/payroll_adjustments_schema.sql').read_text()
                for statement in re.sub(r'--[^\n]*','',source).split(';'):
                    if statement.strip() and not re.match(r'\s*USE\b',statement,re.I):cur.execute(statement)
                db.commit()
            sql("INSERT INTO roles(role_id,role_name) VALUES(9901,'Synthetic freshness approver')")
            sql("INSERT INTO users(user_id,role_id,username,password_hash) SELECT 9901,9901,'freshness-approver',password_hash FROM users WHERE user_id=1")
            sql("INSERT INTO role_permissions SELECT 9901,permission_id FROM permissions WHERE permission_code IN ('payroll.view','payroll.approve','payroll.pay')")
            sql("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='payroll.view'")
            fixture={}
            for index,key in enumerate(('stale','valid','legacy'),7011):
                sql("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES(%s,%s,'Synthetic','Freshness')",(index,'BROWSER-FRESH-'+str(index)))
                compensation=sql("INSERT INTO employee_compensation(employee_id,pay_type,basic_rate,effective_date,created_by) VALUES(%s,'MONTHLY',1000,'2026-01-01',1)",(index,))
                period=sql("INSERT INTO payroll_periods(period_number,period_name,start_date,end_date,pay_date,status,created_by) VALUES(%s,%s,'2026-01-01','2026-01-15','2026-01-16',%s,1)",('BROWSER-FRESH-'+str(index),'Browser freshness '+key,'APPROVED' if key=='legacy' else 'DRAFT'))
                sql("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,generated_by,status,net_pay) VALUES(%s,%s,%s,'MONTHLY',1000,1,%s,123)",(period,index,compensation,'APPROVED' if key=='legacy' else 'DRAFT'))
                fixture[key]=period
                if key=='legacy':continue
                day=date(2026,1,1)
                while day<=date(2026,1,15):
                    if day.weekday()<5:
                        identity=erp.create_attendance_record(index,day,None,None,'PRESENT',None,1)
                        if key=='stale' and day==date(2026,1,5):fixture['attendance']=identity
                    day+=timedelta(days=1)
                erp.calculate_monthly_payroll_period(period,1)
            before_legacy=sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s',(fixture['legacy'],),True)
            root=review.harness.ROOT
            source=(root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source='const FRESH_DIALOGS=[],FRESH_ERRORS=[];\n'+source
            event_marker='    if (!message.id) return;'
            assert source.count(event_marker)==1
            source=source.replace(event_marker,"""    if(message.method==='Page.javascriptDialogOpening') {
      FRESH_DIALOGS.push(message.params.message);
      send('Page.handleJavaScriptDialog',{accept:true},message.sessionId).catch(console.error);
    }
    if(message.method==='Runtime.exceptionThrown') FRESH_ERRORS.push(message.params.exceptionDetails.text);
"""+event_marker)
            source=source.replace("await send('Page.enable', {}, sessionId);","await send('Page.enable', {}, sessionId);\n    await send('Runtime.enable',{},sessionId);")
            source=source.replace("require('./browser_it_authorization.cjs')",'require('+json.dumps(str(root/'tests/browser_it_authorization.cjs'))+')')
            marker="    console.log('SUCCESS: browser execution"
            assert source.count(marker)==1
            addition='    await require('+json.dumps(str(root/'tests/browser_payroll_freshness.cjs'))+')({send,tab,evaluate,navigate,until,fixture:'+json.dumps(fixture)+',dialogs:FRESH_DIALOGS,errors:FRESH_ERRORS});\n'
            source=source.replace(marker,addition+marker)
            script=Path(folder)/'payroll_freshness.cjs';script.write_text(source,encoding='utf-8')
            kwargs['timeout']=420
            result=original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode==0:
                for key,expected in (('stale','APPROVED'),('valid','PAID'),('legacy','APPROVED')):
                    assert sql('SELECT status FROM payroll_periods WHERE payroll_period_id=%s',(fixture[key],),True)==[(expected,)]
                assert sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s',(fixture['legacy'],),True)==before_legacy
                assert sql("SELECT COUNT(*) FROM audit_logs WHERE module='PAYROLL' AND action='MARK_PAID' AND entity_id=%s",(str(fixture['stale']),),True)==[(0,)]
                print('PASS Chrome persisted statuses, unchanged legacy values and no success audit for blocked payment')
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run=review.run
            review.harness.main()


if __name__=='__main__':
    main()
