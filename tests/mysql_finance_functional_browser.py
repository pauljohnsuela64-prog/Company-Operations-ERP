"""Finance native Chrome regressions composed with the disposable security runner.

No company configuration/database is used. The existing runner owns MySQL,
Flask, Chrome, temporary profiles and cleanup. No browser security flags change.
"""
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import mysql_security_review as review


def main():
    original = subprocess.run
    with tempfile.TemporaryDirectory(prefix='erp_finance_functional_') as folder:
        def browser(args, *positional, **kwargs):
            if not isinstance(args, list) or not any(str(arg).endswith('browser_security_review.cjs') for arg in args):
                return original(args, *positional, **kwargs)
            # Called only after the disposable runner patches the connection factory.
            import database
            with database.get_connection() as connection:
                cur = connection.cursor()
                cur.execute("INSERT INTO departments(department_code,department_name) VALUES ('FINFORM','Finance form department')")
                department = cur.lastrowid
                cur.execute("INSERT INTO suppliers(supplier_code,supplier_name) VALUES ('FINFORM','Finance form supplier')")
                supplier = cur.lastrowid
                cur.execute("INSERT INTO purchase_orders(po_number,supplier_id,created_by) VALUES ('FINFORM',%s,1)", (supplier,))
                po = cur.lastrowid
                cur.execute("SELECT category_id FROM expense_categories WHERE category_code='REVIEW'")
                category = cur.fetchone()[0]
                cur.execute("INSERT INTO role_permissions SELECT 3,permission_id FROM permissions WHERE permission_code='finance.view'")
                for year, amount in [(2024,'999999.99'),(2025,'1000000.00'),(2026,'1000000.01')]:
                    cur.execute('INSERT INTO department_budgets(department_id,budget_year,budget_amount,created_by) VALUES (%s,%s,1000000,1)', (department,year))
                    if year == 2025:
                        budget = cur.lastrowid
                    cur.execute("INSERT INTO expenses(expense_number,expense_date,category_id,department_id,description,amount,status,created_by) VALUES (%s,%s,%s,%s,'Synthetic exact boundary',%s,'PAID',1)", (f'BOUNDARY-{year}',f'{year}-01-01',category,department,amount))
                connection.commit()
                cur.close()
            fixture = dict(base=args[2], department=department, supplier=supplier, po=po, category=category, budget=budget)
            root = review.harness.ROOT
            source = (root/'tests/browser_security_review.cjs').read_text(encoding='utf-8')
            source = source.replace("require('./browser_it_authorization.cjs')", 'require('+json.dumps(str(root/'tests/browser_it_authorization.cjs'))+')')
            call = '    await require('+json.dumps(str(root/'tests/browser_finance_functional.cjs'))+')({send, tab, evaluate, navigate, until, submit, fixture:'+json.dumps(fixture)+'});\n'
            marker = "    console.log('SUCCESS: browser execution"
            assert source.count(marker) == 1
            source = source.replace(marker, call+marker)
            script = Path(folder)/'browser_finance_functional.cjs'
            script.write_text(source, encoding='utf-8')
            kwargs['timeout'] = 300
            result = original([args[0],str(script),*args[2:]], *positional, **kwargs)
            if result.returncode == 0:
                with database.get_connection() as connection:
                    cur = connection.cursor()
                    cur.execute("SELECT department_id,supplier_id,purchase_order_id,payment_method,amount FROM expenses WHERE description='Finance correction browser'")
                    from decimal import Decimal
                    assert cur.fetchall() == [(department,supplier,po,'CHECK',Decimal('0.30'))]
                    cur.execute("SELECT action FROM audit_logs WHERE module='FINANCE' AND entity_type='EXPENSE' ORDER BY audit_log_id")
                    assert cur.fetchall() == [('CREATE',),('UPDATE',)]
                    cur.execute('SELECT COUNT(*) FROM department_budgets WHERE budget_year=2029')
                    assert cur.fetchone() == (0,)
                    print('PASS Chrome persisted recovery: one intended linked expense, one CREATE/UPDATE audit, zero forged budget writes')
            return result

        with patch.object(subprocess, 'run', side_effect=browser):
            review.harness.run = review.run
            review.harness.main()


if __name__ == '__main__':
    main()
