"""Inventory catalog real-browser checks on the existing verified disposable security server.

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
    with tempfile.TemporaryDirectory(prefix='erp_gui_inventory_') as folder:
        def browser(args, *positional, **kwargs):
            if not isinstance(args, list) or not any(str(a).endswith('browser_security_review.cjs') for a in args):
                return original(args, *positional, **kwargs)
            import database
            import app as erp
            from flask import request
            item_page, category_page = erp.get_inventory_item_page, erp.get_inventory_category_page

            def page(reader, error):
                def read(filters):
                    # Test-only storage outage; production route/error handler stays intact.
                    if request.args.get('__gui_outage') == '1':
                        raise error('Synthetic isolated storage outage')
                    return reader(filters)
                return read

            with database.get_connection() as db:
                cur = db.cursor()
                cur.executemany("INSERT INTO inventory_categories(category_code,category_name,description,is_active) VALUES(%s,%s,%s,0)", [(f'CAT-HISTORY-{i:04d}', ('<img src=x onerror=alert(1)>'+'C'*70) if i==0 else f'Historical {i:04d}', 'D'*255) for i in range(121)])
                cur.executemany("INSERT INTO inventory_items(item_code,item_name,description,is_active) VALUES(%s,%s,%s,0)", [(f'ITEM-HISTORY-{i:04d}', ('<img src=x onerror=alert(1)>'+'I'*120) if i==0 else f'Historical {i:04d}', 'D'*255) for i in range(121)])
                cur.execute("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='inventory.view'")
                db.commit()
                snapshots = {}
                for table, condition, key in [('inventory_categories',"category_code LIKE 'CAT-HISTORY-%'",'category_id'),('inventory_items',"item_code LIKE 'ITEM-HISTORY-%'",'item_id'),('inventory_stock','1=1','item_id,warehouse_id'),('stock_movements','1=1','movement_id'),('purchase_orders','1=1','purchase_order_id')]:
                    cur.execute(f'SELECT * FROM {table} WHERE {condition} ORDER BY {key}')
                    snapshots[(table,condition,key)] = cur.fetchall()
            root = review.harness.ROOT
            source = (root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
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
            for name in ('browser_inventory_categories.cjs','browser_inventory_items.cjs'):
                additions += '    await require('+json.dumps(str(root/'tests'/name))+')({send,tab,evaluate,navigate,until});\n'
            additions += '    await require('+json.dumps(str(root/'tests/browser_gui_inventory_catalog.cjs'))+')({send,tab,evaluate,navigate,until,errors:GUI_ERRORS,dialogs:GUI_DIALOGS,setConfirm:value=>{GUI_CONFIRM=value;},artifacts:'+json.dumps(str(artifacts))+'});\n'
            source = source.replace(marker, additions+marker)
            script = Path(folder)/'gui_inventory_security.cjs'
            script.write_text(source,encoding='utf-8')
            kwargs['timeout'] = 480
            with patch.object(erp,'get_inventory_item_page',side_effect=page(item_page,erp.ItemDatabaseError)), patch.object(erp,'get_inventory_category_page',side_effect=page(category_page,erp.CategoryDatabaseError)):
                result = original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode == 0:
                with database.get_connection() as db:
                    cur = db.cursor()
                    for (table,condition,key), expected in snapshots.items():
                        cur.execute(f'SELECT * FROM {table} WHERE {condition} ORDER BY {key}')
                        assert cur.fetchall() == expected, table
                    for table, entity, code, key in [('inventory_categories','INVENTORY_CATEGORY','CAT-BROWSER','category_id'),('inventory_items','INVENTORY_ITEM','ITEM-BROWSER','item_id')]:
                        cur.execute(f'SELECT {key},is_active FROM {table} WHERE '+('item_code' if table=='inventory_items' else 'category_code')+'=%s',(code,))
                        identity, active = cur.fetchone(); assert active == 1
                        cur.execute('SELECT action,description FROM audit_logs WHERE entity_type=%s AND entity_id=%s ORDER BY audit_log_id',(entity,str(identity)))
                        events = cur.fetchall()
                        assert [e[0] for e in events] == ['CREATE','UPDATE','DEACTIVATE','ACTIVATE','DEACTIVATE','ACTIVATE'], events
                        assert all('PRIVATE' not in e[1] and '<img' not in e[1] for e in events)
                print('PASS Chrome Inventory: history/stock/movement/PO snapshots unchanged and exact committed audits')
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run = review.run
            review.harness.main()


if __name__ == '__main__':
    main()
