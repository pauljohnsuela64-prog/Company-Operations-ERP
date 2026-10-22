"""HR navigation/dashboard checks composed with isolated Chrome security review."""
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import mysql_security_review as review


def main():
    original = subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_dashboard_browser_') as folder:
        def browser(args, *positional, **kwargs):
            if not isinstance(args, list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args, *positional, **kwargs)
            # The review factory is already bound to its verified fresh server.
            import database
            with database.get_connection() as db:
                cur = db.cursor()
                cur.execute("INSERT INTO roles(role_id,role_name) VALUES(9,'HR Manager')")
                cur.execute("INSERT INTO users(user_id,role_id,username,password_hash) SELECT 9,9,'hr.dashboard',password_hash FROM users WHERE user_id=1")
                cur.execute("INSERT INTO role_permissions SELECT 9,permission_id FROM permissions WHERE permission_code IN ('employees.view','departments.view','attendance.view','leave.view')")
                db.commit()
                cur.execute('SELECT * FROM payroll_periods ORDER BY payroll_period_id'); periods = cur.fetchall()
                cur.execute('SELECT * FROM role_permissions ORDER BY role_id,permission_id'); grants = cur.fetchall()
                cur.execute("SELECT COUNT(*) FROM role_permissions rp JOIN permissions p ON p.permission_id=rp.permission_id WHERE rp.role_id=9 AND p.permission_code IN ('users.manage','roles.manage','audit_logs.view','payroll.view')")
                assert cur.fetchone()[0] == 0
                cur.execute('RENAME TABLE payroll_periods TO dashboard_browser_saved_payroll')
            root = review.harness.ROOT
            source = (root / 'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source = source.replace("require('./browser_it_authorization.cjs')", 'require(' + json.dumps(str(root / 'tests/browser_it_authorization.cjs')) + ')')
            marker = "    console.log('SUCCESS: browser execution"
            assert source.count(marker) == 1
            source = source.replace(marker, '    await require(' + json.dumps(str(root / 'tests/browser_navigation_dashboard.cjs')) + ')({send,tab,evaluate,navigate,until});\n' + marker)
            script = Path(folder) / 'navigation_dashboard_security.cjs'
            script.write_text(source, encoding='utf-8'); kwargs['timeout'] = 360
            try:
                result = original([args[0], str(script), *args[2:]], *positional, **kwargs)
            finally:
                with database.get_connection() as db:
                    cur = db.cursor(); cur.execute('RENAME TABLE dashboard_browser_saved_payroll TO payroll_periods')
            if result.returncode == 0:
                with database.get_connection() as db:
                    cur = db.cursor()
                    cur.execute('SELECT * FROM payroll_periods ORDER BY payroll_period_id'); assert cur.fetchall() == periods
                    # Existing IT security checks deliberately revoke these two
                    # synthetic management grants, and do not change HR grants.
                    cur.execute('SELECT rp.role_id,rp.permission_id FROM role_permissions rp JOIN permissions p ON p.permission_id=rp.permission_id ORDER BY rp.role_id,rp.permission_id')
                    actual = cur.fetchall()
                    cur.execute("SELECT permission_id FROM permissions WHERE permission_code IN ('it_assets.manage','helpdesk.manage')")
                    revoked = {row[0] for row in cur.fetchall()}
                    assert actual == [row for row in grants if not (row[0] == 5 and row[1] in revoked)]
                print('PASS Chrome fixture Payroll history preserved; HR permissions unchanged and no Administration grants')
            return result
        with patch.object(subprocess, 'run', side_effect=browser):
            review.harness.run = review.run
            review.harness.main()


if __name__ == '__main__': main()
