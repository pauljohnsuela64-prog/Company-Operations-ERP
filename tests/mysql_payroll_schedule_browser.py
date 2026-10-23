"""Compose late scheduling conflicts with the verified disposable Chrome runner."""
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import mysql_security_review as review


def main():
    original = subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_cleanup_payroll_browser_') as folder:
        def browser(args, *positional, **kwargs):
            if not isinstance(args, list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args, *positional, **kwargs)
            import app as erp
            import database
            import payroll_period_repository as repo
            # Another synthetic writer commits after HTTP preflight. The actual
            # repository must then detect that conflict inside its transaction.
            def create(**values):
                if values['period_name'] == 'Browser late conflict <safe>':
                    repo.create_payroll_period(**dict(values, period_name='Concurrent browser fixture'))
                return repo.create_payroll_period(**values)
            def update(**values):
                if values['period_name'] == 'Browser late edit <safe>':
                    repo.create_payroll_period(values['period_name'] + ' fixture', values['start_date'], values['end_date'],
                                              values['pay_date'], None, values['updated_by'])
                return repo.update_payroll_period(**values)
            with database.get_connection() as db:
                cur = db.cursor()
                cur.execute("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='payroll.view'")
                db.commit()
            root = review.harness.ROOT
            source = (root / 'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source = source.replace("require('./browser_it_authorization.cjs')", 'require(' + json.dumps(str(root / 'tests/browser_it_authorization.cjs')) + ')')
            marker = "    console.log('SUCCESS: browser execution"
            assert source.count(marker) == 1
            source = source.replace(marker, '    await require(' + json.dumps(str(root / 'tests/browser_payroll_schedule.cjs')) + ')({send,tab,evaluate,navigate,until});\n' + marker)
            script = Path(folder) / 'payroll_schedule.cjs'
            script.write_text(source, encoding='utf-8')
            kwargs['timeout'] = 360
            with ExitStack() as stack:
                stack.enter_context(patch.object(erp, 'create_payroll_period', side_effect=create))
                stack.enter_context(patch.object(erp, 'update_payroll_period', side_effect=update))
                result = original([args[0], str(script), *args[2:]], *positional, **kwargs)
            if result.returncode == 0:
                with database.get_connection() as db:
                    cur = db.cursor()
                    cur.execute("SELECT period_name,start_date FROM payroll_periods WHERE period_name LIKE 'Browser%' ORDER BY period_name")
                    rows = cur.fetchall()
                    assert len(rows) == 2 and rows[0][0] == 'Browser late edit <safe> fixture' and rows[1][0] == 'Browser valid revised', rows
                    cur.execute("SELECT COUNT(*) FROM payroll_periods a JOIN payroll_periods b ON a.payroll_period_id<b.payroll_period_id AND a.start_date<=b.end_date AND a.end_date>=b.start_date WHERE a.status<>'CANCELLED' AND b.status<>'CANCELLED'")
                    assert cur.fetchone() == (0,)
                print('PASS persisted Payroll schedule: no overlapping active periods or denied browser writes')
            return result
        with patch.object(subprocess, 'run', side_effect=browser):
            review.harness.run = review.run
            review.harness.main()


if __name__ == '__main__':
    main()
