"""Remaining-module real-browser checks on the existing verified disposable security server.

Supply ERP_GUI_BOOTSTRAP_CSS (existing 5.3.8 asset) and ERP_GUI_SCREENSHOTS.
No configured/company database or external browser resource is used.
"""
import argparse
import sys
import base64
from gui_contracts import watch_contracts
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import mysql_security_review as review


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['stock','finance','hr','it','admin','all'])
    args_phase = parser.parse_args().phase
    sys.argv = [sys.argv[0]]
    vendor = Path(os.environ['ERP_GUI_BOOTSTRAP_CSS']).read_text(encoding='utf-8')
    assert 'Bootstrap v5.3.8' in ' '.join(vendor.split())
    artifacts = Path(os.environ['ERP_GUI_SCREENSHOTS']).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    original = subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_gui_v1_') as folder:
        def browser(args, *positional, **kwargs):
            if not isinstance(args, list) or not any(str(a).endswith('browser_security_review.cjs') for a in args):
                return original(args, *positional, **kwargs)
            import database
            import app as erp
            from flask import request


            with database.get_connection() as db:
                cur = db.cursor()
                # Synthetic reader fixture only; production grants are untouched.
                cur.execute("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code IN ('inventory.view','finance.view','employees.view','departments.view','attendance.view','leave.view','it_assets.view','helpdesk.view','audit_logs.view')")
                cur.execute("INSERT INTO inventory_items(item_id,item_code,item_name,unit_of_measure) VALUES(990,'GUI-LONG',%s,'pcs')", ('<script>long</script>'+'I'*120,))
                cur.execute("INSERT INTO warehouses(warehouse_id,warehouse_code,warehouse_name,location) VALUES(990,'GUI-WH',%s,%s)", ('W'*100,'L'*255))
                cur.execute('INSERT INTO inventory_stock(item_id,warehouse_id,quantity) VALUES(990,990,12.34)')
                db.commit()
                snapshots = {}
                for table in ('inventory_stock','stock_movements','purchase_orders'):
                    cur.execute(f'SELECT * FROM {table} ORDER BY 1,2')
                    snapshots[table] = cur.fetchall()
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
            additions = '    await require('+json.dumps(str(root/'tests/browser_gui_v1.cjs'))+')({send,tab,evaluate,navigate,until,errors:GUI_ERRORS,phase:'+json.dumps(args_phase)+',artifacts:'+json.dumps(str(artifacts))+'});\n'
            source = source.replace(marker, additions+marker)
            script = Path(folder)/'gui_v1_security.cjs'
            script.write_text(source,encoding='utf-8')
            kwargs['timeout'] = 900
            with watch_contracts(['inventory/stock/','finance/','employees/','departments/','attendance/','leave/','payroll/','it_assets/','help_desk/','admin/','security/','login.html']) as checked:
                result = original([args[0],str(script),*args[2:]],*positional,**kwargs)
            if result.returncode == 0:
                assert checked, 'No baseline contracts checked'
                with database.get_connection() as db:
                    cur = db.cursor()
                    for table, expected in snapshots.items():
                        cur.execute(f'SELECT * FROM {table} ORDER BY 1,2')
                        # The base security workflow may write its own manual stock;
                        # the long-text fixture must remain exactly unchanged.
                        actual = cur.fetchall()
                        if table == 'inventory_stock':
                            assert [r for r in actual if r[0] == 990] == [r for r in expected if r[0] == 990]
                print('PASS GUI baseline form/link/script contracts:', ', '.join(sorted(checked)))
            return result
        with patch.object(subprocess,'run',side_effect=browser):
            review.harness.run = review.run
            review.harness.main()


if __name__ == '__main__':
    main()
