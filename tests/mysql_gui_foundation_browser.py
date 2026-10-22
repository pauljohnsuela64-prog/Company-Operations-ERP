"""Compose existing isolated security/HR checks with Phase 1 visual verification.

Requires an explicit temporary copy of the existing Bootstrap 5.3.8 stylesheet.
No application settings, company DB or external browser requests are used.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import mysql_navigation_dashboard_browser as navigation_review


def main():
    vendor = Path(os.environ['ERP_GUI_BOOTSTRAP_CSS']).read_text(encoding='utf-8')
    assert 'Bootstrap v5.3.8' in ' '.join(vendor.split())
    artifacts = Path(os.environ['ERP_GUI_SCREENSHOTS']).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    original_run = subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_gui_review_') as folder:
        def browser(args, *positional, **kwargs):
            if not isinstance(args, list) or not any(str(arg).endswith('navigation_dashboard_security.cjs') for arg in args):
                return original_run(args, *positional, **kwargs)
            import app as erp
            import dashboard_repository as repository
            from flask import request
            real_read = repository._read_section

            def read(section, today):
                # Auth/permission-scoped production route, synthetic view-only data.
                if request.args.get('__gui_fixture') == 'zero':
                    _, _, _, states, total = repository.SECTIONS[section]
                    result = dict.fromkeys(states, 0)
                    if total:
                        result[total] = 0
                    if section == 'inventory': result['active_items'] = 0
                    if section == 'helpdesk': result.update(open=0, urgent_open=0)
                    if section == 'payroll': result['latest_paid'] = None
                    return result
                return real_read(section, today)

            script_source = Path(args[1]).read_text(encoding='utf-8')
            # Serve the exact existing CDN asset over CDP, keeping all other HTTPS
            # requests blocked. No TLS flags or browser isolation are weakened.
            script_source = script_source.replace("    if (!message.id) return;", """    if (message.method === 'Fetch.requestPaused') {
      const p=message.params;
      if(p.request.url === 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css') {
        send('Fetch.fulfillRequest',{requestId:p.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/css'}],body:GUI_BOOTSTRAP},message.sessionId).catch(console.error);
      } else send('Fetch.failRequest',{requestId:p.requestId,errorReason:'BlockedByClient'},message.sessionId).catch(console.error);
      return;
    }
    if (message.method === 'Runtime.exceptionThrown') GUI_ERRORS.push(message.params.exceptionDetails.text);
    if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') GUI_ERRORS.push('console.error');
    if (!message.id) return;""")
            import base64
            script_source = 'const GUI_ERRORS=[]; const GUI_BOOTSTRAP=' + json.dumps(base64.b64encode(vendor.encode()).decode()) + ';\n' + script_source
            script_source = script_source.replace("await send('Network.setBlockedURLs', {urls:['https://*']}, sessionId);", "await send('Fetch.enable', {patterns:[{urlPattern:'https://*'}]}, sessionId);\n    await send('Runtime.enable', {}, sessionId);")
            marker = "    console.log('SUCCESS: browser execution"
            assert script_source.count(marker) == 1
            module = navigation_review.review.harness.ROOT / 'tests/browser_gui_foundation.cjs'
            script_source = script_source.replace(marker, '    await require(' + json.dumps(str(module)) + ')({send,tab,evaluate,navigate,until,errors:GUI_ERRORS,artifacts:' + json.dumps(str(artifacts)) + '});\n' + marker)
            script = Path(folder) / 'gui_security.cjs'
            script.write_text(script_source, encoding='utf-8')
            with patch.object(repository, '_read_section', side_effect=read):
                return original_run([args[0], str(script), *args[2:]], *positional, **kwargs)
        with patch.object(subprocess, 'run', side_effect=browser):
            navigation_review.main()


if __name__ == '__main__':
    main()
