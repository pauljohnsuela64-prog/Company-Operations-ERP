"""Chrome/Edge semantics checks using the verified synthetic security server."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import mysql_security_review as review


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', choices=('chrome','edge'), default='chrome')
    browser_name = parser.parse_args().browser
    sys.argv = [sys.argv[0]]
    vendor = Path(os.environ['ERP_GUI_BOOTSTRAP_CSS']).read_text(encoding='utf-8')
    assert 'Bootstrap v5.3.8' in ' '.join(vendor.split())
    original_run, original_popen = subprocess.run, subprocess.Popen
    with tempfile.TemporaryDirectory(prefix='erp_release_accessibility_') as folder:
        def launch(args, *positional, **kwargs):
            if browser_name == 'edge' and isinstance(args,list) and str(args[0]).lower().endswith('chrome.exe'):
                edge = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
                assert edge.is_file(), 'Edge unavailable; do not claim cross-browser PASS'
                args = [str(edge),*args[1:]]
            return original_popen(args,*positional,**kwargs)

        def browser(args,*positional,**kwargs):
            if not isinstance(args,list) or not any(str(a).endswith('browser_security_review.cjs') for a in args):
                return original_run(args,*positional,**kwargs)
            root = review.harness.ROOT
            source = (root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source = 'const RELEASE_CSS='+json.dumps(base64.b64encode(vendor.encode()).decode())+';\n'+source
            marker = '    if (!message.id) return;'
            assert source.count(marker)==1
            source = source.replace(marker,"""    if(message.method==='Fetch.requestPaused') {
      const p=message.params;
      if(p.request.url==='https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css') send('Fetch.fulfillRequest',{requestId:p.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/css'}],body:RELEASE_CSS},message.sessionId).catch(console.error);
      else send('Fetch.failRequest',{requestId:p.requestId,errorReason:'BlockedByClient'},message.sessionId).catch(console.error);
      return;
    }
"""+marker)
            source = source.replace("await send('Network.setBlockedURLs', {urls:['https://*']}, sessionId);", "await send('Fetch.enable',{patterns:[{urlPattern:'https://*'}]},sessionId);")
            source = source.replace("require('./browser_it_authorization.cjs')",'require('+json.dumps(str(root/'tests/browser_it_authorization.cjs'))+')')
            marker = "    console.log('SUCCESS: browser execution"
            assert source.count(marker)==1
            source = source.replace(marker,'    await require('+json.dumps(str(root/'tests/browser_release_accessibility.cjs'))+')({send,tab,evaluate,navigate,until});\n'+marker)
            script = Path(folder)/'release_accessibility.cjs';script.write_text(source,encoding='utf-8')
            kwargs['timeout']=600
            return original_run([args[0],str(script),*args[2:]],*positional,**kwargs)
        with patch.object(subprocess,'run',side_effect=browser), patch.object(subprocess,'Popen',side_effect=launch):
            review.harness.run=review.run
            review.harness.main()


if __name__=='__main__':main()
