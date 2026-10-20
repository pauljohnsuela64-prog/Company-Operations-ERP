r"""Explicit disposable-server smoke test; never connects to configured ERP databases.

Run: .venv\Scripts\python.exe tests/mysql_audit_smoke.py
Requires the local Windows MySQL server binary, overridable with --mysqld.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timedelta
import importlib
import os
from pathlib import Path
import re
import socket
import shutil
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
             "payroll_approval", "audit_logs"]
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
                target_id = sql("INSERT INTO payroll_periods(period_number,period_name,start_date,end_date,pay_date,status,created_by) VALUES (%s,%s,'2026-01-01','2026-01-01','2026-01-02',%s,7)", (identifier, identifier, status))
                sql("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,status,generated_by,calculated_at) VALUES (%s,9,1,'MONTHLY',1000,%s,7,NOW())", (target_id, "APPROVED" if case.action == "MARK_PAID" else "CALCULATED"))
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


class IsolationError(RuntimeError):
    """Never shut down an endpoint that is not our held disposable process."""


def print_server_log(folder):
    path = folder / 'server.log'
    if path.exists():
        with path.open('rb') as log:
            log.seek(max(0, path.stat().st_size - 8000))
            print(log.read().decode(errors='replace'), file=sys.stderr, flush=True)


def verify_server(connection, data_dir, process):
    with connection.cursor() as cursor:
        cursor.execute("SELECT @@datadir, @@pid_file")
        actual_dir, pid_file = cursor.fetchone()
    if Path(actual_dir).resolve() != data_dir.resolve():
        raise IsolationError("Disposable MySQL datadir mismatch; refusing shutdown/termination")
    pid_path = Path(pid_file).resolve()
    if pid_path.parent != data_dir.resolve() or int(pid_path.read_text().strip()) != process.pid:
        raise IsolationError("Disposable MySQL PID mismatch; refusing shutdown/termination")


def stop_server(process, port, data_dir, verified):
    """Only the held, SQL/PID-verified child may be terminated; never kill by name."""
    if process.poll() is not None:
        if process.returncode:
            raise RuntimeError(f"Disposable MySQL exited unexpectedly: {process.returncode}")
        return
    if not verified:
        raise IsolationError("Disposable MySQL identity unverified; retaining server and files")
    try:
        with mysql.connector.connect(host="127.0.0.1", port=port, user="root", password="",
                                     connection_timeout=2, read_timeout=3, write_timeout=3) as connection:
            # Recheck immediately before SQL SHUTDOWN. An identity mismatch must
            # propagate, never enter the fallback termination path.
            verify_server(connection, data_dir, process)
            with connection.cursor() as cursor:
                cursor.execute("SHUTDOWN")
    except mysql.connector.Error as error:
        # The listener may already be gone during shutdown. The startup check
        # still binds this Popen handle to this datadir/PID, even without SQL.
        print(f"Disposable MySQL shutdown connection failed: {type(error).__name__}", file=sys.stderr, flush=True)
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        print("Disposable MySQL graceful shutdown timed out; terminating verified child", file=sys.stderr, flush=True)
        print_server_log(data_dir.parent)
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired as error:
                raise RuntimeError("Disposable MySQL termination failed; files retained") from error
        print(f"Disposable MySQL fallback exit status: {process.returncode}", flush=True)
    else:
        if process.returncode:
            raise RuntimeError(f"Disposable MySQL shutdown exit status: {process.returncode}")
        print("Disposable MySQL graceful shutdown complete (exit 0)", flush=True)
    if process.poll() is None:
        raise RuntimeError("Disposable MySQL still running; files retained")


def remove_stopped_directory(folder):
    """Called only after process exit; retry transient Windows handle release."""
    deadline = time.monotonic() + 3
    while True:
        try:
            shutil.rmtree(folder)
            return
        except OSError as error:
            if (os.name != 'nt' or getattr(error, 'winerror', None) not in (5, 32, 145)
                    or time.monotonic() >= deadline):
                raise
            time.sleep(0.1)


@contextmanager
def disposable_server(mysqld):
    # No TemporaryDirectory finalizer: failed termination must NEVER delete live
    # InnoDB files, including when the interpreter exits after an assertion.
    folder = Path(tempfile.mkdtemp(prefix="erp_audit_smoke_"))
    data_dir = folder / "data"
    log_path = folder / "server.log"
    process = None
    stopped = False
    verified = False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        initialized = subprocess.run([mysqld, "--no-defaults", "--initialize-insecure", f"--datadir={data_dir}"], capture_output=True, creationflags=flags)
        if initialized.returncode:
            raise RuntimeError("Disposable MySQL initialization failed: " + initialized.stderr.decode(errors="replace"))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with log_path.open('wb') as log:
            command = [mysqld, "--no-defaults", f"--datadir={data_dir}", f"--pid-file={data_dir / 'disposable.pid'}",
                       f"--port={port}", "--bind-address=127.0.0.1", "--mysqlx=OFF", "--skip-log-bin", "--console"]
            if os.name == 'nt':
                # MySQL >=8.0.12: keep Popen's held handle on the actual server,
                # rather than a restart monitor with a separately living child.
                command.append('--no-monitor')
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            try:
                deadline = time.monotonic() + 25
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Disposable server exited before startup")
                    try:
                        with mysql.connector.connect(host="127.0.0.1", port=port, user="root", password="",
                                                     connection_timeout=1, read_timeout=3, write_timeout=3) as connection:
                            verify_server(connection, data_dir, process)
                        verified = True
                        break
                    except mysql.connector.Error:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.2)
                print(f"Isolated MySQL started: verified loopback/datadir/PID {process.pid}", flush=True)
                yield port, data_dir
            finally:
                stop_server(process, port, data_dir, verified)
                stopped = True
    finally:
        if process is None or stopped:
            remove_stopped_directory(folder)
            print("Disposable MySQL temporary directory removed after process exit", flush=True)
        else:
            print(f"FAILED disposable MySQL cleanup; files retained at {folder}", file=sys.stderr, flush=True)
            print_server_log(folder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mysqld", default=r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe")
    args = parser.parse_args()
    with disposable_server(args.mysqld) as (port, data_dir):
        run(port, data_dir)


if __name__ == "__main__":
    main()
