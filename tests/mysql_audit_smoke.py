r"""Explicit disposable-server smoke test; never connects to configured ERP databases.

Run: .venv\Scripts\python.exe tests/mysql_audit_smoke.py
Requires the local Windows MySQL server binary, overridable with --mysqld.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import date, datetime, timedelta
import importlib
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_business_audit import ACTIONS, SECRETS


from security_helpers import csrf_client

def run(port, data_dir):
    options = dict(host="127.0.0.1", port=port, user="root", password="", connection_timeout=3)
    server = mysql.connector.connect(**options)
    cursor = server.cursor()
    cursor.execute("SELECT @@datadir")
    assert Path(cursor.fetchone()[0]).resolve() == data_dir.resolve(), "Isolation check failed"
    schema = "erp_audit_smoke"
    cursor.execute(f"CREATE DATABASE {schema}")
    cursor.execute(f"USE {schema}")
    files = ["core", "inventory", "procurement", "finance", "budget", "attendance",
             "leave", "payroll", "payroll_period", "payroll_entries", "payroll_calculation",
             "payroll_approval", "payroll_adjustments", "audit_logs"]
    for name in files:
        sql = (ROOT / "database" / f"{name}_schema.sql").read_text()
        sql = re.sub(r"--[^\n]*", "", sql)
        for statement in sql.split(";"):
            statement = statement.strip()
            if not statement or re.match(r"(?:CREATE DATABASE|USE)\b", statement, re.I):
                continue
            assert "company_operations_erp" not in statement
            cursor.execute(statement)
    cursor.execute("INSERT INTO roles(role_id,role_name) VALUES (41,'Acting role'),(42,'Operations'),(43,'Denied role')")
    cursor.execute("INSERT INTO users(user_id,role_id,username,password_hash,is_active) VALUES (7,41,'acting.user','test-only',1),(8,43,'denied.user','test-only',1),(42,42,'target.user','test-only',0)")
    cursor.execute("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES (9,'SMOKE-9','Smoke','Employee')")
    cursor.execute("INSERT INTO employee_compensation(compensation_id,employee_id,pay_type,basic_rate,effective_date,created_by) VALUES (1,9,'MONTHLY',1000,'2026-01-01',7)")
    cursor.execute("INSERT INTO expense_categories(category_id,category_code,category_name) VALUES (1,'SMOKE','Smoke')")
    cursor.execute("INSERT INTO inventory_items(item_id,item_code,item_name,unit_of_measure) VALUES (1,'SMOKE','Smoke','pcs')")
    server.commit()
    cursor.close()
    server.close()
    options["database"] = schema

    def connect():
        # Closure only contains this newly started loopback server's settings.
        return mysql.connector.connect(**options)

    def sql(statement, params=(), fetch=False):
        with connect() as connection:
            cur = connection.cursor(dictionary=True)
            cur.execute(statement, params)
            result = cur.fetchall() if fetch else cur.lastrowid
            connection.commit()
            cur.close()
            return result

    with ExitStack() as stack:
        stack.enter_context(patch("dotenv.load_dotenv", return_value=False))
        stack.enter_context(patch.dict(os.environ, {"SECRET_KEY": "isolated-smoke-key", "ERP_ENV": "testing", "ERP_DEBUG": "false"}))
        database = importlib.import_module("database")
        stack.enter_context(patch.object(database, "get_connection", side_effect=connect))
        erp = importlib.import_module("app")
        stack.enter_context(patch.dict(erp.app.config, TESTING=True))
        stack.enter_context(patch.object(erp.app.logger, "exception"))
        # All repository imports bind to the isolated factory above. No business
        # operation, identifier lookup, template, or audit writer is mocked.
        permissions = sorted({case.permission for case in ACTIONS} | {"audit_logs.view"})

        for permission in permissions:
            pid = sql("INSERT INTO permissions(permission_code) VALUES (%s) ON DUPLICATE KEY UPDATE permission_id=LAST_INSERT_ID(permission_id)", (permission,))
            sql("INSERT INTO role_permissions(role_id,permission_id) VALUES (41,%s)", (pid,))

        def client(allowed=True):
            c = csrf_client(erp.app)
            with c.session_transaction() as sess:
                from security_helpers import user_state, stamp_session
                state = user_state(user_id=7 if allowed else 8, username="acting.user" if allowed else "denied.user", role_id=41 if allowed else 43)
                stamp_session(erp.app, sess, state)
                sess.update(**SECRETS)
                # Secrets must not override the acting user's identity.
            return c

        def logs():
            return sql("SELECT * FROM audit_logs ORDER BY audit_log_id", fetch=True)

        serial = 0

        def fixture(case):
            nonlocal serial
            serial += 1
            identifier = case.identifier
            target_id = 42
            if case.module == "PAYROLL":
                status = {"SUBMIT": "DRAFT", "RETURN_TO_DRAFT": "PROCESSING", "APPROVE": "PROCESSING", "MARK_PAID": "APPROVED"}[case.action]
                identifier = f"PAY-SMOKE-{serial}"
                target_id = sql("INSERT INTO payroll_periods(period_number,period_name,start_date,end_date,pay_date,status,created_by) VALUES (%s,%s,'2026-01-01','2026-01-01','2026-01-02','DRAFT',7)", (identifier, identifier))
                sql("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,status,generated_by) VALUES (%s,9,1,'MONTHLY',1000,'DRAFT',7)", (target_id,))
                sql("INSERT IGNORE INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(9,'2026-01-01','PRESENT',7)")
                erp.calculate_monthly_payroll_period(target_id,7)
                if status=='APPROVED':sql("UPDATE payroll_entries SET status='APPROVED' WHERE payroll_period_id=%s",(target_id,))
                sql('UPDATE payroll_periods SET status=%s WHERE payroll_period_id=%s',(status,target_id))
            elif case.module == "LEAVE":
                target_id, identifier = erp.create_leave_request(9, 1, date(2026, 2, 1) + timedelta(days=serial), date(2026, 2, 1) + timedelta(days=serial), 1, SECRETS["reason"], 7)
            elif case.module == "PROCUREMENT":
                target_id, identifier = erp.create_purchase_request(7, None, "Smoke")
                erp.add_purchase_request_item(target_id, 1, 1, 10)
                if case.action != "SUBMIT":
                    sql("UPDATE purchase_requests SET status='SUBMITTED' WHERE request_id=%s", (target_id,))
            elif case.module == "FINANCE":
                target_id, identifier = erp.create_expense(date(2026, 1, 1), 1, None, None, None, "Smoke", 10, None, "CASH", 7, None)
                if case.action == "MARK_PAID":
                    sql("UPDATE expenses SET status='APPROVED' WHERE expense_id=%s", (target_id,))
            return case.path.replace("/42/", f"/{target_id}/"), identifier, target_id

        form = {**SECRETS, "confirm_password": SECRETS["password"], "username": "new.smoke.user", "role_id": "42"}
        expected = []
        for case in ACTIONS:
            path, identifier, target_id = fixture(case)
            if case.name == "user_create":
                identifier = form["username"]
            before = len(logs())
            assert client(False).post(path, data=form).status_code == 302
            assert len(logs()) == before, case.name + " unauthorized event"
            response = client().post(path, data=form)
            assert response.status_code == 302, case.name
            rows = logs()
            assert len(rows) == before + 1, (case.name, response.status_code, rows[before:])
            row = rows[-1]
            assert tuple(row[k] for k in ("user_id", "username", "module", "action", "entity_type", "entity_id")) == (7, "acting.user", case.module, case.action, case.entity, identifier), row
            assert isinstance(row["created_at"], datetime)
            now = sql("SELECT NOW() AS now", fetch=True)[0]["now"]
            assert abs((now - row["created_at"]).total_seconds()) < 10
            for secret in SECRETS.values():
                assert secret not in repr(row)
            expected.append(row)
            if case.module in {"PAYROLL", "LEAVE", "PROCUREMENT", "FINANCE"}:
                assert client().post(path, data=form).status_code == 302
                assert len(logs()) == before + 1, case.name + " repeated event"
            print("PASS persisted + unauthorized:", case.name)

        # Invalid form and an actual duplicate-key transaction must not log success.
        before = len(logs())
        assert client().post("/admin/users/add", data={**form, "password": "short"}).status_code == 200
        assert client().post("/admin/users/add", data=form).status_code == 302
        assert len(logs()) == before
        print("PASS validation and actual duplicate-key failure: no audit rows")

        # Concurrent approvals/payments contend on actual InnoDB row locks/updates.
        for name in ("payroll_approve", "payroll_paid", "leave_approve", "purchase_approve", "expense_approve", "expense_paid"):
            case = next(c for c in ACTIONS if c.name == name)
            path, identifier, target_id = fixture(case)
            barrier = threading.Barrier(2)
            def submit():
                c = client()
                barrier.wait(timeout=10)
                return c.post(path, data=form).status_code
            before = len(logs())
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(submit) for _ in range(2)]
                assert [f.result(timeout=20) for f in futures] == [302, 302]
            assert len(logs()) == before + 1, name + " concurrent duplicate"
            print("PASS concurrent transition:", name)

        # Force a genuine SQL insert error while the business database stays usable.
        case = next(c for c in ACTIONS if c.name == "expense_approve")
        path, identifier, target_id = fixture(case)
        before = len(logs())
        sql("CREATE TRIGGER smoke_reject_audit BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='isolated audit failure'")
        try:
            assert client().post(path, data=form).status_code == 302
            assert sql("SELECT status FROM expenses WHERE expense_id=%s", (target_id,), True)[0]["status"] == "APPROVED"
            assert len(logs()) == before
        finally:
            sql("DROP TRIGGER smoke_reject_audit")
        print("PASS real audit SQL failure: business approval remains committed")

        # Real repository filtering and real Jinja HTML rendering over persisted rows.
        from audit_log_repository import get_filtered_audit_logs
        all_rows = logs()
        selected = get_filtered_audit_logs(module="PAYROLL", action="APPROVE")
        assert len(selected) == 2 and all(r["module"] == "PAYROLL" and r["action"] == "APPROVE" for r in selected)
        assert len(get_filtered_audit_logs(search_text="new.smoke.user")) == 1
        today = sql("SELECT CURRENT_DATE AS today", fetch=True)[0]["today"]
        assert len(get_filtered_audit_logs(start_date=today, end_date=today)) == len(all_rows)
        assert get_filtered_audit_logs(start_date=today + timedelta(days=1)) == []
        ordered = get_filtered_audit_logs()
        assert [(r["created_at"], r["audit_log_id"]) for r in ordered] == sorted(((r["created_at"], r["audit_log_id"]) for r in all_rows), reverse=True)
        html = client().get("/admin/audit-logs?module=PAYROLL&action=APPROVE").get_data(as_text=True)
        assert "PAY-SMOKE" in html and expected[10]["entity_id"] not in html
        searched = client().get("/admin/audit-logs?search=new.smoke.user").get_data(as_text=True)
        assert "new.smoke.user" in searched and "PAY-SMOKE" not in searched
        dated = client().get(f"/admin/audit-logs?start_date={today}&end_date={today}")
        assert dated.status_code == 200 and expected[0]["entity_id"] in dated.get_data(as_text=True)
        html_all = client().get("/admin/audit-logs").get_data(as_text=True)
        # Use distinct identifiers to check HTML order independent of same-target
        # rows, which may legitimately recur across separate actions.
        newest = all_rows[-1]["entity_id"]
        oldest = all_rows[0]["entity_id"]
        assert html_all.index(newest) < html_all.index(oldest)
        assert "No audit log records found." in client().get("/admin/audit-logs?search=no-such-smoke-record").get_data(as_text=True)
        assert client(False).get("/admin/audit-logs").status_code == 302
        # Prove the existing 500-row cap and banner, not nonexistent pagination.
        with connect() as connection:
            cur = connection.cursor()
            cur.executemany("INSERT INTO audit_logs(user_id,username,module,action,entity_type,entity_id) VALUES (7,'acting.user','SMOKE','CAP','TEST',%s)", [(str(i),) for i in range(501)])
            connection.commit()
            cur.close()
        assert len(get_filtered_audit_logs(module="SMOKE")) == 500
        response = client().get("/admin/audit-logs?module=SMOKE")
        assert response.status_code == 200
        assert "Showing the latest 500 matching records." in response.get_data(as_text=True)
        print("PASS persisted search/module/action/date filters, ordering, Jinja page, permissions, and 500-row cap (no pagination exists)")
        print("SUCCESS: disposable MySQL smoke checks completed; no configured ERP database accessed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mysqld", default=r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="erp_audit_smoke_") as folder:
        data_dir = Path(folder) / "data"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        initialized = subprocess.run([args.mysqld, "--no-defaults", "--initialize-insecure", f"--datadir={data_dir}"], capture_output=True, creationflags=flags)
        if initialized.returncode:
            raise RuntimeError("Disposable MySQL initialization failed: " + initialized.stderr.decode(errors="replace"))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([args.mysqld, "--no-defaults", f"--datadir={data_dir}", f"--port={port}", "--bind-address=127.0.0.1", "--mysqlx=OFF", "--skip-log-bin", "--console"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        try:
            deadline = time.monotonic() + 25
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Disposable server exited before startup")
                try:
                    connection = mysql.connector.connect(host="127.0.0.1", port=port, user="root", password="", connection_timeout=1)
                    connection.close()
                    break
                except mysql.connector.Error:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.2)
            print("Isolated MySQL started on loopback with fresh temporary datadir")
            run(port, data_dir)
        finally:
            if process.poll() is None:
                # MySQL on Windows may use a supervisor/child process. Request a
                # graceful shutdown of the verified instance before waiting.
                connection = mysql.connector.connect(host="127.0.0.1", port=port, user="root", password="", connection_timeout=2)
                cur = connection.cursor()
                cur.execute("SELECT @@datadir")
                assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve()
                cur.execute("SHUTDOWN")
                connection.close()
                process.wait(timeout=20)


if __name__ == "__main__":
    main()
