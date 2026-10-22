"""Procurement workflow real-browser checks on the existing verified disposable security server.

Supply ERP_GUI_BOOTSTRAP_CSS (existing 5.3.8 asset) and ERP_GUI_SCREENSHOTS.
No configured/company database or external browser resource is used.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import mysql_security_review as review


def main():
    vendor = Path(os.environ['ERP_GUI_BOOTSTRAP_CSS']).read_text(encoding='utf-8')
    assert 'Bootstrap v5.3.8' in ' '.join(vendor.split())
    artifacts = Path(os.environ['ERP_GUI_SCREENSHOTS']).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    original = subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_gui_procurement_') as folder:
        def browser(args, *positional, **kwargs):
            if not isinstance(args, list) or not any(str(a).endswith('browser_security_review.cjs') for a in args):
                return original(args, *positional, **kwargs)
            import database
            with database.get_connection() as db:
                cur=db.cursor()
                cur.execute("INSERT INTO roles(role_id,role_name) VALUES(7,'Procurement Manager'),(8,'Procurement Approver')")
                for uid,role,name in [(70,7,'procurement.manager'),(80,8,'procurement.approver')]:
                    cur.execute("INSERT INTO users(user_id,role_id,username,password_hash) SELECT %s,%s,%s,password_hash FROM users WHERE user_id=1",(uid,role,name))
                for role,codes in [(7,['procurement.view','procurement.requests.create','procurement.orders.manage','procurement.receipts.manage']),(8,['procurement.view','procurement.requests.approve']),(2,['procurement.view'])]:
                    for code in codes:
                        cur.execute('INSERT INTO role_permissions SELECT %s,permission_id FROM permissions WHERE permission_code=%s',(role,code))
                cur.execute("INSERT INTO departments(department_id,department_code,department_name) VALUES(900,'GUI-PROC','Procurement review department')")
                cur.execute("INSERT INTO inventory_items(item_id,item_code,item_name,unit_of_measure) VALUES(900,'GUI-ITEM','GUI Equipment','pcs'),(901,'GUI-SECOND','Second review item','pcs')")
                cur.execute("INSERT INTO warehouses(warehouse_id,warehouse_code,warehouse_name) VALUES(900,'GUI-WH','Review warehouse')")
                cur.execute("INSERT INTO suppliers(supplier_id,supplier_code,supplier_name,is_active) VALUES(900,'GUI-ACTIVE','Review supplier',1),(901,'GUI-INACTIVE','Inactive review supplier',0)")
                db.commit()
                cur.execute('SELECT * FROM expenses ORDER BY expense_id'); expenses=cur.fetchall()
                cur.execute('SELECT * FROM role_permissions WHERE role_id IN (7,8) ORDER BY role_id,permission_id');grants=cur.fetchall()
            root = review.harness.ROOT
            source = (root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            # The unchanged IT browser suite is outside this Procurement review;
            # retain the base login/session/CSRF checks and the full PR/PO/GR flow.
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
            additions = ''
            additions += '    await require('+json.dumps(str(root/'tests/browser_gui_procurement.cjs'))+')({send,tab,evaluate,navigate,until,errors:GUI_ERRORS,dialogs:GUI_DIALOGS,setConfirm:value=>{GUI_CONFIRM=value;},artifacts:'+json.dumps(str(artifacts))+'});\n'
            source = source.replace(marker, additions+marker)
            script = Path(folder)/'gui_procurement_security.cjs'
            script.write_text(source,encoding='utf-8')
            kwargs['timeout'] = 480
            result = original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode == 0:
                from decimal import Decimal
                with database.get_connection() as db:
                    cur=db.cursor()
                    cur.execute('SELECT quantity FROM inventory_stock WHERE item_id=900 AND warehouse_id=900');assert cur.fetchone()[0]==Decimal('10.25')
                    cur.execute('SELECT COUNT(*),SUM(quantity_received) FROM goods_receipt_items gri JOIN purchase_order_items poi ON poi.purchase_order_item_id=gri.purchase_order_item_id WHERE poi.item_id=900');assert cur.fetchone()==(2,Decimal('10.25'))
                    cur.execute('SELECT COUNT(*) FROM goods_receipts');assert cur.fetchone()[0]==2
                    cur.execute("SELECT COUNT(*) FROM stock_movements WHERE item_id=900 AND movement_type='IN'");assert cur.fetchone()[0]==2
                    cur.execute("SELECT COUNT(*) FROM audit_logs WHERE entity_type='GOODS_RECEIPT' AND action='RECEIVE'");assert cur.fetchone()[0]==2
                    cur.execute('SELECT * FROM expenses ORDER BY expense_id');assert cur.fetchall()==expenses
                    cur.execute('SELECT * FROM role_permissions WHERE role_id IN (7,8) ORDER BY role_id,permission_id');assert cur.fetchall()==grants
                print('PASS Procurement GUI DB proof: exactly 2 receipts/stock movements/audits, total 10.25, no replay duplicates, Finance history and requester/approver grants unchanged')
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run = review.run
            review.harness.main()


if __name__ == '__main__':
    main()
