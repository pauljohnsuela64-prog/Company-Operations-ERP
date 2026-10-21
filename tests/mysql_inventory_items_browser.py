"""Inventory Items Chrome workflow composed with the existing isolated security runner."""
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import mysql_security_review as review


def main():
    original=subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_items_browser_') as folder:
        def browser(args,*positional,**kwargs):
            if not isinstance(args,list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args,*positional,**kwargs)
            import database
            with database.get_connection() as db:
                cur=db.cursor()
                cur.executemany("INSERT INTO inventory_items(item_code,item_name,description,is_active) VALUES(%s,%s,'Historical <img src=x>',0)",[(f'ITEM-HISTORY-{i:04d}',f'Historical {i:04d}') for i in range(121)])
                cur.execute("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='inventory.view'")
                db.commit()
                cur.execute("SELECT * FROM inventory_items WHERE item_code LIKE 'ITEM-HISTORY-%' ORDER BY item_id");before=cur.fetchall()
            root=review.harness.ROOT
            source=(root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source=source.replace("require('./browser_it_authorization.cjs')",'require('+json.dumps(str(root/'tests/browser_it_authorization.cjs'))+')')
            marker="    console.log('SUCCESS: browser execution"
            assert source.count(marker)==1
            source=source.replace(marker,'    await require('+json.dumps(str(root/'tests/browser_inventory_items.cjs'))+')({send,tab,evaluate,navigate,until});\n'+marker)
            script=Path(folder)/'browser_inventory_items.cjs';script.write_text(source,encoding='utf-8')
            kwargs['timeout']=360
            result=original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode==0:
                with database.get_connection() as db:
                    cur=db.cursor()
                    cur.execute("SELECT * FROM inventory_items WHERE item_code LIKE 'ITEM-HISTORY-%' ORDER BY item_id");assert cur.fetchall()==before
                    cur.execute("SELECT item_id,item_name,is_active FROM inventory_items WHERE item_code='ITEM-BROWSER'");identity,name,active=cur.fetchone()
                    assert (name,active)==('PRIVATE revised item',1)
                    cur.execute("SELECT action,description FROM audit_logs WHERE entity_type='INVENTORY_ITEM' AND entity_id=%s ORDER BY audit_log_id",(str(identity),));events=cur.fetchall()
                    assert [row[0] for row in events]==['CREATE','UPDATE','DEACTIVATE','ACTIVATE'],events
                    assert all('PRIVATE' not in row[1] and '<img' not in row[1] for row in events)
                print('PASS Chrome Items historical fixtures unchanged and exactly four committed business audits, no failed/no-op/denied success events')
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run=review.run
            review.harness.main()


if __name__=='__main__':main()
