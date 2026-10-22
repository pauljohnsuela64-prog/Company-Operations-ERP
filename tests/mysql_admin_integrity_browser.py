"""Administration native Chrome checks composed with isolated security/IT review."""
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import mysql_security_review as review


def main():
    original = subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_admin_browser_') as folder:
        def browser(args, *positional, **kwargs):
            if not isinstance(args, list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args, *positional, **kwargs)
            # This hook runs only after review.run binds the verified fresh DB.
            import database
            with database.get_connection() as db:
                cur = db.cursor()
                cur.execute("INSERT INTO users(role_id,username,password_hash) VALUES(2,'admin.browser.target','synthetic-browser-unused')")
                target = cur.lastrowid
                db.commit()
                cur.execute('SELECT user_id,role_id,is_active,password_hash FROM users ORDER BY user_id')
                before = cur.fetchall()
            root = review.harness.ROOT
            source = (root / 'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source = source.replace("require('./browser_it_authorization.cjs')", 'require(' + json.dumps(str(root / 'tests/browser_it_authorization.cjs')) + ')')
            marker = "    console.log('SUCCESS: browser execution"
            assert source.count(marker) == 1
            source = source.replace(marker, '    await require(' + json.dumps(str(root / 'tests/browser_admin_integrity.cjs')) + ')({send,tab,evaluate,navigate,until});\n' + marker)
            script = Path(folder) / 'admin_security_review.cjs'
            script.write_text(source, encoding='utf-8')
            kwargs['timeout'] = 360
            result = original([args[0], str(script), *args[2:]], *positional, **kwargs)
            if result.returncode == 0:
                with database.get_connection() as db:
                    cur = db.cursor()
                    cur.execute('SELECT role_id,is_active,password_hash FROM users WHERE user_id=%s', (target,))
                    assert cur.fetchone() == (2, 1, 'synthetic-browser-unused')
                    cur.execute("SELECT action,description FROM audit_logs WHERE module='ADMINISTRATION' AND entity_id='admin.browser.target' ORDER BY audit_log_id")
                    events = cur.fetchall()
                    assert [e[0] for e in events] == ['DEACTIVATE', 'ACTIVATE', 'UPDATE', 'UPDATE'], events
                    assert all('synthetic' not in e[1] and 'password' not in e[1] for e in events)
                    # Existing IT browser deliberately disables user 5; other
                    # original account memberships/passwords must be preserved.
                    cur.execute('SELECT user_id,role_id,is_active,password_hash FROM users WHERE user_id<>5 ORDER BY user_id')
                    assert cur.fetchall() == [row for row in before if row[0] != 5]
                print('PASS Chrome persisted exactly four changed account audits; passwords, original memberships and final target state preserved')
            return result
        with patch.object(subprocess, 'run', side_effect=browser):
            review.harness.run = review.run
            review.harness.main()


if __name__ == '__main__': main()
