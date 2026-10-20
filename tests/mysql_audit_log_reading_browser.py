"""Audit Logs Chrome checks composed with the verified disposable security runner."""
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import mysql_security_review as review


def main():
    original=subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_audit_browser_') as folder:
        def browser(args,*positional,**kwargs):
            if not isinstance(args,list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args,*positional,**kwargs)
            import database
            with database.get_connection() as db:
                cur=db.cursor()
                cur.executemany("INSERT INTO audit_logs(user_id,username,module,action,entity_type,entity_id,description,created_at) VALUES(NULL,'Archived auditor','BROWSER_AUDIT','READ','RECORD',%s,'BROWSER-AUDIT <img src=x onerror=alert(1)>','2020-01-01 12:00:00')",[(f'HIST-{i:04d}',) for i in range(1005)])
                db.commit()
                cur.execute("SELECT * FROM audit_logs WHERE module='BROWSER_AUDIT' ORDER BY audit_log_id")
                before=cur.fetchall()
            root=review.harness.ROOT
            source=(root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source=source.replace("require('./browser_it_authorization.cjs')",'require('+json.dumps(str(root/'tests/browser_it_authorization.cjs'))+')')
            marker="    console.log('SUCCESS: browser execution"
            assert source.count(marker)==1
            call='    await require('+json.dumps(str(root/'tests/browser_audit_logs.cjs'))+')({send,tab,evaluate,navigate,until});\n'
            source=source.replace(marker,call+marker)
            script=Path(folder)/'browser_audit_logs.cjs'
            script.write_text(source,encoding='utf-8')
            kwargs['timeout']=360
            result=original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode==0:
                with database.get_connection() as db:
                    cur=db.cursor()
                    cur.execute("SELECT * FROM audit_logs WHERE module='BROWSER_AUDIT' ORDER BY audit_log_id")
                    assert cur.fetchall()==before
                print('PASS Chrome Audit Logs historical rows unchanged after navigation, invalid filters and permission denial')
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run=review.run
            review.harness.main()


if __name__=='__main__':main()
