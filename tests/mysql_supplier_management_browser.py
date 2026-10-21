"""Supplier Chrome workflow composed with the existing isolated security runner."""
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import mysql_security_review as review


def main():
    original=subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_supplier_browser_') as folder:
        def browser(args,*positional,**kwargs):
            if not isinstance(args,list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args,*positional,**kwargs)
            import database
            with database.get_connection() as db:
                cur=db.cursor()
                cur.executemany("INSERT INTO suppliers(supplier_code,supplier_name,address,is_active) VALUES(%s,%s,'Historical <img src=x>',0)",[(f'SUP-HISTORY-{i:04d}',f'Historical {i:04d}') for i in range(121)])
                cur.execute("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='procurement.view'")
                db.commit()
                cur.execute("SELECT * FROM suppliers WHERE supplier_code LIKE 'SUP-HISTORY-%' ORDER BY supplier_id");before=cur.fetchall()
                cur.execute('SELECT * FROM purchase_orders ORDER BY purchase_order_id');assignments=cur.fetchall()
            root=review.harness.ROOT
            source=(root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source=source.replace("require('./browser_it_authorization.cjs')",'require('+json.dumps(str(root/'tests/browser_it_authorization.cjs'))+')')
            marker="    console.log('SUCCESS: browser execution"
            assert source.count(marker)==1
            source=source.replace(marker,'    await require('+json.dumps(str(root/'tests/browser_supplier_management.cjs'))+')({send,tab,evaluate,navigate,until});\n'+marker)
            script=Path(folder)/'browser_supplier_management.cjs';script.write_text(source,encoding='utf-8')
            kwargs['timeout']=360
            result=original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode==0:
                with database.get_connection() as db:
                    cur=db.cursor()
                    cur.execute("SELECT * FROM suppliers WHERE supplier_code LIKE 'SUP-HISTORY-%' ORDER BY supplier_id");assert cur.fetchall()==before
                    cur.execute('SELECT * FROM purchase_orders ORDER BY purchase_order_id');assert cur.fetchall()==assignments
                    cur.execute("SELECT supplier_id,supplier_name,is_active FROM suppliers WHERE supplier_code='SUP-BROWSER'");identity,name,active=cur.fetchone()
                    assert (name,active)==('PRIVATE revised supplier',1)
                    cur.execute("SELECT action,description FROM audit_logs WHERE entity_type='SUPPLIER' AND entity_id=%s ORDER BY audit_log_id",(str(identity),));events=cur.fetchall()
                    assert [row[0] for row in events]==['CREATE','UPDATE','DEACTIVATE','ACTIVATE'],events
                    assert all('PRIVATE' not in row[1] and '<img' not in row[1] for row in events)
                    cur.execute("SELECT contact_person,email,phone,address FROM suppliers WHERE supplier_code='SUP-OPTIONAL'");assert cur.fetchone()==(None,None,None,None)
                print('PASS Chrome Suppliers historical fixtures unchanged and exactly four committed business audits, no failed/no-op/denied success events')
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run=review.run
            review.harness.main()


if __name__=='__main__':main()
