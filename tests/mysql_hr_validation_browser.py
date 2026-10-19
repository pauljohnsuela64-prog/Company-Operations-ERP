"""Compose HR Chrome checks with the existing disposable security runner."""
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import mysql_security_review as review


def main():
    original = subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_hr_browser_') as folder:
        def browser(args, *positional, **kwargs):
            if not isinstance(args, list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args, *positional, **kwargs)
            # The review runner has already verified its disposable datadir and
            # patched the connection factory. No configured company DB is used.
            import database
            with database.get_connection() as connection:
                cur = connection.cursor()
                cur.execute("INSERT INTO departments(department_code,department_name) VALUES('HR-FIXTURE','HR fixture')")
                department = cur.lastrowid
                cur.execute("INSERT INTO roles(role_id,role_name) VALUES(7,'HR browser viewer')")
                cur.execute("INSERT INTO role_permissions SELECT 7,permission_id FROM permissions WHERE permission_code IN ('employees.view','departments.view','dashboard.view')")
                cur.execute("INSERT INTO users(role_id,username,password_hash) SELECT 7,'hr-viewer',password_hash FROM users WHERE user_id=1")
                connection.commit()
                cur.close()
            root=review.harness.ROOT
            source=(root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source=source.replace("require('./browser_it_authorization.cjs')", 'require('+json.dumps(str(root/'tests/browser_it_authorization.cjs'))+')')
            call='    await require('+json.dumps(str(root/'tests/browser_hr_validation.cjs'))+')({send,tab,evaluate,navigate,until,fixture:'+json.dumps(dict(department=department))+'});\n'
            marker="    console.log('SUCCESS: browser execution"
            assert source.count(marker)==1
            source=source.replace(marker,call+marker)
            script=Path(folder)/'browser_hr_validation.cjs'
            script.write_text(source,encoding='utf-8')
            kwargs['timeout']=300
            result=original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode==0:
                with database.get_connection() as connection:
                    cur=connection.cursor()
                    cur.execute("SELECT department_id,phone,employment_status FROM employees WHERE employee_number='HR-BROWSER-EMP'")
                    assert cur.fetchall()==[(department,'Corrected phone','Active')]
                    cur.execute("SELECT description,is_active FROM departments WHERE department_code='HR-BROWSER'")
                    assert cur.fetchall()==[('Corrected browser department',1)]
                    cur.execute("SELECT COUNT(*) FROM employees WHERE employee_number='FORGED-HR'")
                    assert cur.fetchone()==(0,)
                    cur.close()
                print('PASS Chrome persisted employee/department corrections and zero forged employee writes')
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run=review.run
            review.harness.main()


if __name__=='__main__':
    main()
