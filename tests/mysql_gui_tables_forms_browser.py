"""Phase 2 real-browser checks on the existing verified disposable security server.

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
    with tempfile.TemporaryDirectory(prefix='erp_gui_tables_') as folder:
        def browser(args, *positional, **kwargs):
            if not isinstance(args, list) or not any(str(a).endswith('browser_security_review.cjs') for a in args):
                return original(args, *positional, **kwargs)
            import database
            import app as erp
            from flask import request
            supplier_page, category_page = erp.get_supplier_page, erp.get_expense_category_page

            def page(reader, error):
                def read(filters):
                    # Test-only storage outage; production route/error handler stays intact.
                    if request.args.get('__gui_outage') == '1':
                        raise error('Synthetic isolated storage outage')
                    return reader(filters)
                return read

            with database.get_connection() as db:
                cur = db.cursor()
                cur.executemany("INSERT INTO suppliers(supplier_code,supplier_name,contact_person,email,phone,address,is_active) VALUES(%s,%s,%s,%s,%s,'Historical <img src=x>',0)", [(f'SUP-HISTORY-{i:04d}', ('<img src=x onerror=alert(1)>'+'L'*120) if i==0 else f'Historical {i:04d}', 'Contact '+'X'*90,'long.'+'x'*115+'@example.test','P'*30) for i in range(121)])
                cur.executemany("INSERT INTO expense_categories(category_code,category_name,description,is_active) VALUES(%s,%s,%s,0)", [(f'EXP-HISTORY-{i:04d}','Category '+'N'*90 if i==0 else f'Historical {i:04d}','<img src=x onerror=alert(1)>'+'D'*220) for i in range(121)])
                cur.execute("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code IN ('procurement.view','finance.view')")
                db.commit()
                snapshots = {}
                for table, condition, key in [('suppliers',"supplier_code LIKE 'SUP-HISTORY-%'",'supplier_id'),('expense_categories',"category_code LIKE 'EXP-HISTORY-%'",'category_id'),('purchase_orders','1=1','purchase_order_id'),('expenses','1=1','expense_id')]:
                    cur.execute(f'SELECT * FROM {table} WHERE {condition} ORDER BY {key}')
                    snapshots[(table,condition,key)] = cur.fetchall()
            root = review.harness.ROOT
            source = (root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source = source.replace("require('./browser_it_authorization.cjs')", 'require('+json.dumps(str(root/'tests/browser_it_authorization.cjs'))+')')
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
            for name in ('browser_supplier_management.cjs','browser_expense_category_management.cjs'):
                additions += '    await require('+json.dumps(str(root/'tests'/name))+')({send,tab,evaluate,navigate,until});\n'
            additions += '    await require('+json.dumps(str(root/'tests/browser_gui_tables_forms.cjs'))+')({send,tab,evaluate,navigate,until,errors:GUI_ERRORS,dialogs:GUI_DIALOGS,setConfirm:value=>{GUI_CONFIRM=value;},artifacts:'+json.dumps(str(artifacts))+'});\n'
            source = source.replace(marker, additions+marker)
            script = Path(folder)/'gui_tables_security.cjs'
            script.write_text(source,encoding='utf-8')
            kwargs['timeout'] = 480
            with patch.object(erp,'get_supplier_page',side_effect=page(supplier_page,erp.SupplierDatabaseError)), patch.object(erp,'get_expense_category_page',side_effect=page(category_page,erp.ExpenseCategoryDatabaseError)):
                result = original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode == 0:
                with database.get_connection() as db:
                    cur = db.cursor()
                    for (table,condition,key), expected in snapshots.items():
                        cur.execute(f'SELECT * FROM {table} WHERE {condition} ORDER BY {key}')
                        assert cur.fetchall() == expected, table
                    for table, entity, code, key in [('suppliers','SUPPLIER','SUP-BROWSER','supplier_id'),('expense_categories','EXPENSE_CATEGORY','EXP-BROWSER','category_id')]:
                        cur.execute(f'SELECT {key},is_active FROM {table} WHERE '+('supplier_code' if table=='suppliers' else 'category_code')+'=%s',(code,))
                        identity, active = cur.fetchone(); assert active == 1
                        cur.execute('SELECT action,description FROM audit_logs WHERE entity_type=%s AND entity_id=%s ORDER BY audit_log_id',(entity,str(identity)))
                        events = cur.fetchall()
                        assert [e[0] for e in events] == ['CREATE','UPDATE','DEACTIVATE','ACTIVATE','DEACTIVATE','ACTIVATE'], events
                        assert all('PRIVATE' not in e[1] and '<img' not in e[1] for e in events)
                    cur.execute("SELECT contact_person,email,phone,address FROM suppliers WHERE supplier_code='SUP-OPTIONAL'")
                    assert cur.fetchone() == (None,None,None,None)
                print('PASS Phase 2 Chrome: history/PO/expense snapshots unchanged, exact committed audits, optional Supplier fields unchanged')
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run = review.run
            review.harness.main()


if __name__ == '__main__':
    main()
