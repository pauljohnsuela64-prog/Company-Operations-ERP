"""Employee listing + existing HR native Chrome workflows on disposable MySQL."""
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import mysql_security_review as review


def main():
    original=subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_listing_browser_') as folder:
        def browser(args,*positional,**kwargs):
            if not isinstance(args,list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args,*positional,**kwargs)
            import database
            with database.get_connection() as db:
                cur=db.cursor()
                cur.execute("INSERT INTO departments(department_code,department_name) VALUES('HR-FIXTURE','HR fixture')")
                department=cur.lastrowid
                for role,name in [(7,'hr-viewer'),(8,'listing-viewer')]:
                    cur.execute('INSERT INTO roles(role_id,role_name) VALUES(%s,%s)',(role,name))
                    cur.execute("INSERT INTO role_permissions SELECT %s,permission_id FROM permissions WHERE permission_code IN ('employees.view','departments.view','dashboard.view')",(role,))
                    cur.execute('INSERT INTO users(role_id,username,password_hash) SELECT %s,%s,password_hash FROM users WHERE user_id=1',(role,name))
                rows=[(f'LIST-SYN-{i:03d}','Same','ZzzListing') for i in range(63)]
                rows += [('LIST%LITERAL','José','ZzzListing'),('LIST_LITERAL','Other','ZzzListing'),
                         ('LIST!LITERAL','Other','ZzzListing'),('HTML-LIST','<img src=x onerror=alert(1)>','ZzzListing')]
                cur.executemany('INSERT INTO employees(employee_number,first_name,last_name) VALUES(%s,%s,%s)',rows)
                db.commit()
                cur.execute("SELECT * FROM employees WHERE last_name='ZzzListing' ORDER BY employee_id")
                before=cur.fetchall()
            root=review.harness.ROOT
            source=(root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source=source.replace("require('./browser_it_authorization.cjs')",'require('+json.dumps(str(root/'tests/browser_it_authorization.cjs'))+')')
            calls=''
            for script in ('browser_hr_validation.cjs','browser_employee_listing.cjs'):
                calls+='    await require('+json.dumps(str(root/'tests'/script))+')({send,tab,evaluate,navigate,until,fixture:'+json.dumps({'department':department})+'});\n'
            marker="    console.log('SUCCESS: browser execution"
            assert source.count(marker)==1
            source=source.replace(marker,calls+marker)
            script=Path(folder)/'browser_employee_listing.cjs';script.write_text(source,encoding='utf-8')
            kwargs['timeout']=360
            result=original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode==0:
                with database.get_connection() as db:
                    cur=db.cursor();cur.execute("SELECT * FROM employees WHERE last_name='ZzzListing' ORDER BY employee_id")
                    assert cur.fetchall()==before
                print('PASS Chrome listing fixture records/revisions remain unchanged')
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run=review.run
            review.harness.main()


if __name__=='__main__':main()
