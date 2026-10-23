"""The fifteen investigated cases, now enforced as freshness regression contracts.

Composes the unchanged failing audit fixture on verified disposable MySQL.
Requires stale transitions to reject and fresh controls to succeed. Disposable only.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import date, timedelta
import importlib
import threading
import time
from unittest.mock import patch

import mysql_payroll_freshness_audit as audit


class InvestigationComplete(Exception):
    pass


def run(port, data_dir):
    # Import without workstation dotenv settings. audit.run patches every actual
    # business connection to its verified disposable database before any calls.
    with patch('dotenv.load_dotenv', return_value=False):
        workflow = importlib.import_module('payroll_workflow_repository')
        attendance = importlib.import_module('attendance_repository')
        calculation = importlib.import_module('payroll_calculation_repository')
    original_submit = workflow.submit_payroll_for_approval
    observations = []
    serial = 100

    def investigate(original_period, actor):
        import database

        def sql(statement, params=(), fetch=False):
            with database.get_connection() as db:
                cur = db.cursor()
                cur.execute(statement, params)
                result = cur.fetchall() if fetch else cur.lastrowid
                db.commit()
                return result

        def outcome(label, action):
            try:
                action()
                result = 'ACCEPTED'
            except ValueError as error:
                result = 'REJECTED: ' + str(error)
            observations.append((label, result))
            print(label + ': ' + result, flush=True)
            accepted = label in ('edit before calculation (control)',
                                 'explicit recalculation after edit (control)')
            assert result.startswith('ACCEPTED' if accepted else 'REJECTED'), (label, result)

        def fixture(missing=False):
            nonlocal serial
            serial += 1
            number = serial
            employee = sql("INSERT INTO employees(employee_number,first_name,last_name) VALUES(%s,'Synthetic','Freshness')", ('INV-' + str(number),))
            compensation = sql("INSERT INTO employee_compensation(employee_id,pay_type,basic_rate,effective_date,created_by) VALUES(%s,'MONTHLY',1000,'2026-01-01',1)", (employee,))
            period = sql("INSERT INTO payroll_periods(period_number,period_name,start_date,end_date,pay_date,created_by) VALUES(%s,%s,'2026-01-01','2026-01-15','2026-01-16',1)", ('INV-' + str(number), 'Investigation ' + str(number)))
            sql("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,generated_by) VALUES(%s,%s,%s,'MONTHLY',1000,1)", (period, employee, compensation))
            current = date(2026, 1, 1)
            changed = None
            while current <= date(2026, 1, 15):
                if current.weekday() < 5 and not (missing and current == date(2026, 1, 5)):
                    identity = attendance.create_attendance_record(employee, current, None, None, 'PRESENT', None, 1)
                    if current == date(2026, 1, 5):
                        changed = identity
                current += timedelta(days=1)
            return employee, period, changed

        def edit(identity, employee, status, day=date(2026, 1, 5)):
            return attendance.update_attendance_record(identity, employee, day, None, None, status, None, 1)

        def later_edit(identity, employee, status):
            def connect_later():
                db = database.get_connection()
                with db.cursor() as cur:
                    cur.execute('SET timestamp=1768564801')
                return db
            with patch.object(attendance, 'get_connection', side_effect=connect_later):
                return edit(identity, employee, status)

        outcome('same-second edit then submission', lambda: original_submit(original_period, actor))
        outcome('repeated stale submission', lambda: original_submit(original_period, actor))

        employee, period, changed = fixture()
        edit(changed, employee, 'ABSENT')
        calculation.calculate_monthly_payroll_period(period, 1)
        outcome('edit before calculation (control)', lambda: original_submit(period, 1))

        employee, period, changed = fixture()
        calculation.calculate_monthly_payroll_period(period, 1)
        edit(changed, employee, 'ABSENT')
        edit(changed, employee, 'PRESENT')
        outcome('multiple edits returning to original status', lambda: original_submit(period, 1))

        employee, period, changed = fixture()
        calculation.calculate_monthly_payroll_period(period, 1)
        edit(changed, employee, 'ABSENT')
        calculation.calculate_monthly_payroll_period(period, 1)
        outcome('explicit recalculation after edit (control)', lambda: original_submit(period, 1))

        employee, period, changed = fixture()
        calculation.calculate_monthly_payroll_period(period, 1)
        later_edit(changed, employee, 'ABSENT')
        outcome('ordinary later-second edit (control)', lambda: original_submit(period, 1))

        employee, period, changed = fixture()
        calculation.calculate_monthly_payroll_period(period, 1)
        edit(changed, employee, 'PRESENT', date(2026, 1, 17))
        outcome('relevant weekday row moved outside cutoff', lambda: original_submit(period, 1))

        employee, period, changed = fixture()
        calculation.calculate_monthly_payroll_period(period, 1)
        destination = sql("INSERT INTO employees(employee_number,first_name,last_name) VALUES('INV-DEST','Synthetic','Destination')")
        edit(changed, destination, 'PRESENT')
        outcome('relevant row reassigned to another employee', lambda: original_submit(period, 1))
        attendance.create_attendance_record(employee, date(2026, 1, 5), None, None, 'ABSENT', None, 1)
        # The stale first attempt must not have transitioned out of DRAFT.
        assert sql('SELECT status FROM payroll_periods WHERE payroll_period_id=%s', (period,), True) == [('DRAFT',)]
        outcome('replacement attendance inserted after calculation', lambda: original_submit(period, 1))

        employee, period, changed = fixture(missing=True)
        calculation.calculate_monthly_payroll_period(period, 1)
        attendance.create_attendance_record(employee, date(2026, 1, 5), None, None, 'PRESENT', None, 1)
        outcome('insert fills cached unrecorded day (control)', lambda: original_submit(period, 1))

        employee, period, changed = fixture()
        calculation.calculate_monthly_payroll_period(period, 1)
        sql("INSERT INTO permissions(permission_code) SELECT 'payroll.process' WHERE NOT EXISTS(SELECT 1 FROM permissions WHERE permission_code='payroll.process')")
        import payroll_period_repository as periods
        with patch.object(periods, 'get_connection', side_effect=database.get_connection):
            assert periods.update_payroll_period(period, 'Moved cutoff investigation', date(2029, 1, 1),
                                                date(2029, 1, 15), date(2029, 1, 16), None, 1)
        outcome('DRAFT cutoff moved after calculation', lambda: original_submit(period, 1))

        employee, period, changed = fixture()
        calculation.calculate_monthly_payroll_period(period, 1)
        original_submit(period, 1)
        edit(changed, employee, 'ABSENT')
        outcome('same-second edit after submission then approval', lambda: workflow.approve_payroll_period(period, 1))
        workflow.return_payroll_to_draft(period, 1)
        calculation.calculate_monthly_payroll_period(period, 1)
        original_submit(period, 1)
        workflow.approve_payroll_period(period, 1)
        later_edit(changed, employee, 'PRESENT')
        before_payment = sql('SELECT * FROM payroll_periods WHERE payroll_period_id=%s', (period,), True)
        outcome('post-approval edit then payment (policy observation)', lambda: workflow.mark_payroll_period_as_paid(period, 1))
        assert sql('SELECT * FROM payroll_periods WHERE payroll_period_id=%s', (period,), True) == before_payment

        for approval in (False, True):
            employee, period, changed = fixture()
            calculation.calculate_monthly_payroll_period(period, 1)
            if approval:
                original_submit(period, 1)
            entered, release = threading.Event(), threading.Event()

            class HeldCommit:
                def __init__(self, connection):
                    self.connection = connection
                def __getattr__(self, name):
                    return getattr(self.connection, name)
                def commit(self):
                    entered.set()
                    assert release.wait(10), 'Test did not release Payroll commit'
                    return self.connection.commit()

            with patch.object(workflow, 'get_connection', side_effect=lambda: HeldCommit(database.get_connection())):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    transition = workflow.approve_payroll_period if approval else original_submit
                    future = pool.submit(transition, period, 1)
                    try:
                        assert entered.wait(10), 'Payroll did not reach commit'
                        writer = pool.submit(edit, changed, employee, 'ABSENT')
                        deadline = time.monotonic() + 10
                        while not sql("""SELECT COUNT(*) FROM performance_schema.data_lock_waits w
                            JOIN performance_schema.data_locks r ON r.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID AND r.ENGINE=w.ENGINE
                            WHERE r.OBJECT_SCHEMA=DATABASE() AND r.OBJECT_NAME='payroll_attendance_guard'""", fetch=True)[0][0]:
                            assert time.monotonic() < deadline, 'Expected actual Attendance wait on Payroll guard'
                            time.sleep(.02)
                        assert not writer.done() and not future.done()
                    finally:
                        release.set()
                    future.result(timeout=10)
                    writer.result(timeout=10)
                    # Payroll linearized first; the later source write makes
                    # the next transition stale without undoing that commit.
                    next_transition = workflow.mark_payroll_period_as_paid if approval else workflow.approve_payroll_period
                    outcome('concurrent Attendance / ' + ('approval' if approval else 'submission'),
                            lambda: next_transition(period, 1))

        assert len(observations) == 15
        print('PASS all 15 investigated scenarios, including observed transaction guard waits', flush=True)
        extended(sql, fixture, edit, original_submit, database, attendance, calculation, workflow)
        raise InvestigationComplete()

    try:
        with patch.object(workflow, 'submit_payroll_for_approval', side_effect=investigate):
            audit.run(port, data_dir)
    except InvestigationComplete:
        pass
    else:
        raise AssertionError('Investigation callback did not execute')
    print('SUCCESS: scoped Payroll freshness regression, verified disposable MySQL only')


def extended(sql, fixture, edit, submit, database, attendance, calculation, workflow):
    """Failure, scope, legacy, paid history and both race orderings."""
    import mysql.connector
    import payroll_freshness as freshness
    from attendance_validation import AttendanceError

    def rejected(action, message=None):
        try:
            action()
        except ValueError as error:
            if message:
                assert message.lower() in str(error).lower(), str(error)
        else:
            raise AssertionError('Expected freshness rejection')

    employee, period, changed = fixture()
    calculation.calculate_monthly_payroll_period(period, 1)
    attendance.create_attendance_record(employee, date(2026, 2, 1), None, None, 'ABSENT', None, 1)
    other = sql("INSERT INTO employees(employee_number,first_name,last_name) VALUES('OUTSIDE','Other','Employee')")
    attendance.create_attendance_record(other, date(2026, 1, 5), None, None, 'ABSENT', None, 1)
    submit(period, 1)
    rejected(lambda: submit(period, 1), 'Draft')
    workflow.approve_payroll_period(period, 1)
    workflow.mark_payroll_period_as_paid(period, 1)
    paid = sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s', (period,), True)
    edit(changed, employee, 'ABSENT')
    assert sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s', (period,), True) == paid
    rejected(lambda: calculation.calculate_monthly_payroll_period(period, 1), 'Draft')
    print('PASS out-of-scope stability, valid payment, repeated submission guard and unchanged PAID history')

    for state in ('DRAFT', 'PROCESSING', 'APPROVED'):
        employee, period, changed = fixture()
        sql("UPDATE payroll_entries SET status=%s,calculated_at=NOW() WHERE payroll_period_id=%s",
            ('APPROVED' if state == 'APPROVED' else 'CALCULATED', period))
        sql('UPDATE payroll_periods SET status=%s WHERE payroll_period_id=%s', (state, period))
        before = sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s', (period,), True)
        action = {'DRAFT': submit, 'PROCESSING': workflow.approve_payroll_period,
                  'APPROVED': workflow.mark_payroll_period_as_paid}[state]
        rejected(lambda: action(period, 1), 'unverified')
        assert sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s', (period,), True) == before
        assert sql('SELECT status FROM payroll_periods WHERE payroll_period_id=%s', (period,), True) == [(state,)]
    print('PASS legacy NULL evidence blocked at submit, approve and pay without status/amount rewrites')

    employee, period, changed = fixture()
    calculation.calculate_monthly_payroll_period(period, 1)
    sql('DELETE s FROM payroll_attendance_snapshots s JOIN payroll_entries pe ON pe.payroll_entry_id=s.payroll_entry_id WHERE pe.payroll_period_id=%s AND s.attendance_date=%s', (period, date(2026, 1, 5)))
    rejected(lambda: submit(period, 1), 'incomplete')
    calculation.calculate_monthly_payroll_period(period, 1)
    sql('UPDATE payroll_entries SET attendance_evidence_version=2 WHERE payroll_period_id=%s', (period,))
    rejected(lambda: submit(period, 1), 'unverified')
    calculation.calculate_monthly_payroll_period(period, 1)
    submit(period, 1)
    print('PASS incomplete/unknown evidence rejects; only explicit calculation restores valid evidence')

    employee, period, changed = fixture()
    before = sql('SELECT * FROM attendance_records WHERE attendance_id=%s', (changed,), True)
    sql('UPDATE payroll_attendance_generations SET generation=%s WHERE employee_id=%s AND attendance_date=%s',
        (freshness.MAX_GENERATION, employee, date(2026, 1, 5)))
    rejected(lambda: edit(changed, employee, 'ABSENT'), 'exhausted')
    assert sql('SELECT * FROM attendance_records WHERE attendance_id=%s', (changed,), True) == before
    assert sql('SELECT generation FROM payroll_attendance_generations WHERE employee_id=%s AND attendance_date=%s',
               (employee, date(2026, 1, 5)), True) == [(freshness.MAX_GENERATION,)]
    print('PASS generation exhaustion rolls source write back without wrap/reset')

    class CommitFault:
        def __init__(self, connection, after=False):
            self.connection, self.after, self.calls = connection, after, 0
        def __getattr__(self, name):
            return getattr(self.connection, name)
        def commit(self):
            self.calls += 1
            if self.after:
                self.connection.commit()
            raise mysql.connector.InterfaceError('Synthetic uncertain commit', errno=2013)

    for after in (False, True):
        employee, period, changed = fixture()
        calculation.calculate_monthly_payroll_period(period, 1)
        source_before = sql('SELECT * FROM attendance_records WHERE attendance_id=%s', (changed,), True)
        gen_before = sql('SELECT * FROM payroll_attendance_generations WHERE employee_id=%s', (employee,), True)
        proxy = CommitFault(database.get_connection(), after)
        with patch.object(attendance, 'get_connection', return_value=proxy) as factory:
            rejected(lambda: edit(changed, employee, 'ABSENT'), 'confirm')
            factory.assert_called_once()
        assert proxy.calls == 1
        if after:
            assert sql('SELECT * FROM attendance_records WHERE attendance_id=%s', (changed,), True) != source_before
            rejected(lambda: submit(period, 1), 'changed')
        else:
            assert sql('SELECT * FROM attendance_records WHERE attendance_id=%s', (changed,), True) == source_before
            assert sql('SELECT * FROM payroll_attendance_generations WHERE employee_id=%s', (employee,), True) == gen_before
            submit(period, 1)

        employee, period, changed = fixture()
        entries_before = sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s', (period,), True)
        proxy = CommitFault(database.get_connection(), after)
        with patch.object(calculation, 'get_connection', return_value=proxy) as factory:
            try:
                calculation.calculate_monthly_payroll_period(period, 1)
            except mysql.connector.Error:
                pass
            else:
                raise AssertionError('Lost acknowledgment incorrectly reported success')
            factory.assert_called_once()
        assert proxy.calls == 1
        if after:
            # Explicit operator reconciliation discovers the one committed result.
            submit(period, 1)
        else:
            assert sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s', (period,), True) == entries_before
            assert sql('SELECT s.* FROM payroll_attendance_snapshots s JOIN payroll_entries pe ON pe.payroll_entry_id=s.payroll_entry_id WHERE pe.payroll_period_id=%s', (period,), True) == []
    print('PASS source+generation and result+evidence atomicity; lost acknowledgments never automatically retry')

    def wait_for_guard():
        deadline = time.monotonic() + 10
        while not sql("""SELECT COUNT(*) FROM performance_schema.data_lock_waits w
            JOIN performance_schema.data_locks r ON r.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID AND r.ENGINE=w.ENGINE
            WHERE r.OBJECT_SCHEMA=DATABASE() AND r.OBJECT_NAME='payroll_attendance_guard'""", fetch=True)[0][0]:
            assert time.monotonic() < deadline, 'Expected actual integrity guard lock wait'
            time.sleep(.02)

    for isolation in ('REPEATABLE READ', 'READ COMMITTED'):
        def isolated():
            db = database.get_connection()
            with db.cursor() as cur:
                cur.execute('SET SESSION TRANSACTION ISOLATION LEVEL ' + isolation)
            return db
        with ExitStack() as modes:
            for module in (attendance, calculation, workflow):
                modes.enter_context(patch.object(module, 'get_connection', side_effect=isolated))
            for phase in ('calculate', 'submit', 'approve', 'pay'):
                for source_first in (True, False):
                    employee, period, changed = fixture()
                    calculation.calculate_monthly_payroll_period(period, 1)
                    if phase in ('approve', 'pay'):
                        submit(period, 1)
                    if phase == 'pay':
                        workflow.approve_payroll_period(period, 1)
                    transition = {'calculate': calculation.calculate_monthly_payroll_period, 'submit': submit,
                                  'approve': workflow.approve_payroll_period, 'pay': workflow.mark_payroll_period_as_paid}[phase]
                    owner = calculation if phase == 'calculate' else workflow
                    held_module = attendance if source_first else owner
                    entered, release = threading.Event(), threading.Event()
                    class Held:
                        def __init__(self, connection):
                            self.connection = connection
                        def __getattr__(self, name):
                            return getattr(self.connection, name)
                        def commit(self):
                            entered.set()
                            assert release.wait(10)
                            return self.connection.commit()
                    with patch.object(held_module, 'get_connection', side_effect=lambda: Held(isolated())):
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            winner = pool.submit(edit, changed, employee, 'ABSENT') if source_first else pool.submit(transition, period, 1)
                            try:
                                assert entered.wait(10)
                                loser = pool.submit(transition, period, 1) if source_first else pool.submit(edit, changed, employee, 'ABSENT')
                                wait_for_guard()
                                assert not loser.done()
                            finally:
                                release.set()
                            winner.result(timeout=10)
                            if source_first and phase != 'calculate':
                                rejected(lambda: loser.result(timeout=10))
                            else:
                                loser.result(timeout=10)
                            if phase == 'calculate' and source_first:
                                submit(period, 1)
                            elif not source_first and phase != 'pay':
                                next_action = submit if phase == 'calculate' else (
                                    workflow.approve_payroll_period if phase == 'submit' else workflow.mark_payroll_period_as_paid)
                                rejected(lambda: next_action(period, 1))
                    print('PASS observed race', isolation, phase, 'source first' if source_first else 'Payroll first', flush=True)
    print('PASS sixteen real calculation/submit/approve/pay races, both orders and both isolation levels')

    employee, period, changed = fixture()
    calculation.calculate_monthly_payroll_period(period, 1)
    source_before = sql('SELECT * FROM attendance_records WHERE attendance_id=%s', (changed,), True)
    gen_before = sql('SELECT * FROM payroll_attendance_generations WHERE employee_id=%s', (employee,), True)
    with database.get_connection() as blocker:
        blocker.start_transaction()
        cur = blocker.cursor(); cur.execute('SELECT guard_id FROM payroll_attendance_guard WHERE guard_id=1 FOR UPDATE'); cur.fetchone()
        def timeout_connection():
            db = database.get_connection()
            with db.cursor() as cursor:
                cursor.execute('SET SESSION innodb_lock_wait_timeout=1')
            return db
        try:
            with patch.object(attendance, 'get_connection', side_effect=timeout_connection):
                rejected(lambda: edit(changed, employee, 'ABSENT'), 'busy')
            with patch.object(workflow, 'get_connection', side_effect=timeout_connection) as factory:
                try:
                    submit(period, 1)
                except mysql.connector.Error as error:
                    assert error.errno == 1205
                else:
                    raise AssertionError('Expected actual Payroll lock timeout')
                factory.assert_called_once()
        finally:
            blocker.rollback()
    assert sql('SELECT * FROM attendance_records WHERE attendance_id=%s', (changed,), True) == source_before
    assert sql('SELECT * FROM payroll_attendance_generations WHERE employee_id=%s', (employee,), True) == gen_before
    assert sql('SELECT status FROM payroll_periods WHERE payroll_period_id=%s', (period,), True) == [('DRAFT',)]
    submit(period, 1)
    print('PASS actual Attendance/Payroll 1205 guard timeouts roll back without automatic replay')

    # Deliberately opposite-order external writer: prove a real 1213 cannot
    # produce a partial generation/source commit or trigger an automatic retry.
    employee, period, changed = fixture()
    generation = sql('SELECT generation FROM payroll_attendance_generations WHERE employee_id=%s AND attendance_date=%s',
                     (employee,date(2026,1,5)),True)[0][0]
    with database.get_connection() as external, ThreadPoolExecutor(max_workers=1) as pool:
        external.start_transaction()
        cur=external.cursor();cur.execute('SELECT attendance_id FROM attendance_records WHERE attendance_id=%s FOR UPDATE',(changed,));cur.fetchone()
        with patch.object(attendance,'get_connection',side_effect=database.get_connection) as factory:
            future=pool.submit(edit,changed,employee,'ABSENT')
            deadline=time.monotonic()+10
            while not sql("""SELECT COUNT(*) FROM performance_schema.data_lock_waits w
                JOIN performance_schema.data_locks r ON r.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID AND r.ENGINE=w.ENGINE
                WHERE r.OBJECT_SCHEMA=DATABASE() AND r.OBJECT_NAME='attendance_records'""",fetch=True)[0][0]:
                assert time.monotonic()<deadline
                time.sleep(.02)
            external_deadlock=False
            try:
                cur.execute('SELECT guard_id FROM payroll_attendance_guard WHERE guard_id=1 FOR UPDATE')
                cur.fetchone()
            except mysql.connector.Error as error:
                assert error.errno==1213
                external_deadlock=True
            finally:
                external.rollback()
            try:
                future.result(timeout=10)
                committed=True
            except AttendanceError as error:
                assert error.status_code==409
                committed=False
            assert external_deadlock or not committed
            factory.assert_called_once()
    assert sql('SELECT status FROM attendance_records WHERE attendance_id=%s',(changed,),True)==[('ABSENT' if committed else 'PRESENT',)]
    assert sql('SELECT generation FROM payroll_attendance_generations WHERE employee_id=%s AND attendance_date=%s',
               (employee,date(2026,1,5)),True)==[(generation+int(committed),)]
    print('PASS actual external-writer 1213 deadlock: atomic source/generation, no automatic replay')

    # Missing integrity state must not be recreated on a runtime path.
    sql('DELETE FROM payroll_attendance_guard')
    try:
        rejected(lambda: attendance.create_attendance_record(employee, date(2027,1,1), None,None,'PRESENT',None,1), 'coordination')
        assert sql('SELECT * FROM payroll_attendance_guard', fetch=True) == []
    finally:
        sql('INSERT INTO payroll_attendance_guard VALUES(1)')  # Explicit synthetic-fixture repair only.
    print('PASS missing guard fails closed without runtime schema/data repair')

    employee, period, changed = fixture()
    edit(changed, employee, 'ON_LEAVE')
    import leave_repository as leave
    with patch.object(leave,'get_connection',side_effect=database.get_connection):
        kind = leave.create_leave_type('FRESHNESS-LEAVE','Freshness Leave',None,100,True)
        request, _ = leave.create_leave_request(employee,kind,date(2026,1,5),date(2026,1,5),1,'Synthetic',1)
        leave.approve_leave_request(request,1)
        calculation.calculate_monthly_payroll_period(period,1)
        leave.update_leave_type(kind,'FRESHNESS-LEAVE','Freshness Leave',None,100,False)
        rejected(lambda: submit(period,1), 'changed')
    print('PASS real Leave approval and changed paid/unpaid classification invalidate the existing calculation input')


if __name__ == '__main__':
    audit.harness.run = run
    audit.harness.main()
