from security_helpers import user_state, stamp_session
"""Isolated audit regression tests. Run with .venv/Scripts/python -m unittest discover -s tests -v.

Real Flask routes, permission decorators, and audit helper are exercised. Repository
calls are mocked; a connector guard prevents any accidental database connection.
"""

import importlib
import os
import unittest
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date
from unittest.mock import Mock, patch


@dataclass(frozen=True)
class Action:
    name: str
    path: str
    permission: str
    operation: str
    module: str
    action: str
    entity: str
    identifier: str
    lookup: str = ""
    key: str = ""
    active: bool = False


ACTIONS = [
    Action("payroll_submit", "/payroll/periods/42/submit", "payroll.process", "submit_payroll_for_approval", "PAYROLL", "SUBMIT", "PAYROLL_PERIOD", "PAY-0042", "get_payroll_period_by_id", "period_number"),
    Action("payroll_return", "/payroll/periods/42/return-to-draft", "payroll.process", "return_payroll_to_draft", "PAYROLL", "RETURN_TO_DRAFT", "PAYROLL_PERIOD", "PAY-0042", "get_payroll_period_by_id", "period_number"),
    Action("payroll_approve", "/payroll/periods/42/approve", "payroll.approve", "approve_payroll_period", "PAYROLL", "APPROVE", "PAYROLL_PERIOD", "PAY-0042", "get_payroll_period_by_id", "period_number"),
    Action("payroll_paid", "/payroll/periods/42/paid", "payroll.pay", "mark_payroll_period_as_paid", "PAYROLL", "MARK_PAID", "PAYROLL_PERIOD", "PAY-0042", "get_payroll_period_by_id", "period_number"),
    Action("leave_approve", "/leave/requests/42/approve", "leave.approve", "approve_leave_request", "LEAVE", "APPROVE", "LEAVE_REQUEST", "LV-0042", "get_leave_request_by_id", "request_number"),
    Action("leave_reject", "/leave/requests/42/reject", "leave.approve", "reject_leave_request", "LEAVE", "REJECT", "LEAVE_REQUEST", "LV-0042", "get_leave_request_by_id", "request_number"),
    Action("leave_cancel", "/leave/requests/42/cancel", "leave.manage", "cancel_leave_request", "LEAVE", "CANCEL", "LEAVE_REQUEST", "LV-0042", "get_leave_request_by_id", "request_number"),
    Action("purchase_submit", "/procurement/requests/42/submit", "procurement.requests.create", "submit_purchase_request", "PROCUREMENT", "SUBMIT", "PURCHASE_REQUEST", "PR-0042"),
    Action("purchase_approve", "/procurement/requests/42/approve", "procurement.requests.approve", "approve_purchase_request", "PROCUREMENT", "APPROVE", "PURCHASE_REQUEST", "PR-0042"),
    Action("purchase_reject", "/procurement/requests/42/reject", "procurement.requests.approve", "reject_purchase_request", "PROCUREMENT", "REJECT", "PURCHASE_REQUEST", "PR-0042"),
    Action("expense_approve", "/finance/expenses/42/approve", "finance.expenses.approve", "approve_expense", "FINANCE", "APPROVE", "EXPENSE", "EXP-0042", "get_expense_by_id", "expense_number"),
    Action("expense_paid", "/finance/expenses/42/paid", "finance.expenses.pay", "mark_expense_as_paid", "FINANCE", "MARK_PAID", "EXPENSE", "EXP-0042", "get_expense_by_id", "expense_number"),
    Action("user_create", "/admin/users/add", "users.manage", "create_user", "ADMINISTRATION", "CREATE", "USER", "target.user"),
    Action("user_activate", "/admin/users/42/status", "users.manage", "set_user_active_status", "ADMINISTRATION", "ACTIVATE", "USER", "target.user"),
    Action("user_deactivate", "/admin/users/42/status", "users.manage", "set_user_active_status", "ADMINISTRATION", "DEACTIVATE", "USER", "target.user", active=True),
    Action("password_reset", "/admin/users/42/reset-password", "users.manage", "update_user_password", "ADMINISTRATION", "RESET_PASSWORD", "USER", "target.user"),
    Action("role_permissions", "/admin/roles/42/permissions", "roles.manage", "update_role_permissions", "ADMINISTRATION", "UPDATE_PERMISSIONS", "ROLE", "Operations"),
]

SECRETS = {
    "password": "PRIVATE-PASSWORD-123", "password_hash": "PRIVATE-HASH-123",
    "reason": "PRIVATE-LEAVE-REASON", "rejection_reason": "PRIVATE-REJECTION",
    "token": "PRIVATE-TOKEN", "session_secret": "PRIVATE-SESSION-SECRET",
}


class BusinessAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.safety = ExitStack()
        # Patch before importing application/repositories. Never load real .env data.
        cls.safety.enter_context(patch("dotenv.load_dotenv", return_value=False))
        cls.safety.enter_context(patch.dict(os.environ, {"SECRET_KEY": "isolated-audit-test-key", "ERP_ENV": "testing", "ERP_DEBUG": "false"}))
        cls.safety.enter_context(patch("mysql.connector.connect", side_effect=AssertionError("Real database access forbidden in audit tests")))
        cls.addClassCleanup(cls.safety.close)
        cls.erp = importlib.import_module("app")

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config, TESTING=True))
        self.stack.enter_context(patch.object(self.erp.app.logger, "exception"))
        self.stack.enter_context(patch.object(self.erp, "render_template", return_value="test page"))
        self.client = self.erp.app.test_client()

    def mock(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.erp, name, **kwargs))

    def prepare(self, case):
        self.insert = self.mock("create_audit_log")
        self.commits = []

        def committed(*args, **kwargs):
            self.commits.append(case.operation)
            return {"total_entries": 1} if case.module == "PAYROLL" else True

        self.operation = self.mock(case.operation, side_effect=committed)
        self.lookup = None
        if case.lookup:
            self.lookup = self.mock(case.lookup, return_value={case.key: case.identifier, **SECRETS})
        self.purchase = self.mock("get_purchase_request_by_id", return_value={
            "request_number": "PR-0042", "status": "DRAFT" if case.action == "SUBMIT" else "SUBMITTED", **SECRETS,
        })
        self.items = self.mock("get_purchase_request_items", return_value=[{"item_id": 1}])
        self.budget = self.mock("check_expense_against_budget", return_value={"budget_required": False, "can_pay": True})
        self.user = self.mock("get_user_by_id", return_value={"user_id": 42, "username": "target.user", "role_name": "Operations", "is_active": case.active, **SECRETS})
        self.role = self.mock("get_role_by_id", return_value={"role_id": 42, "role_name": "Operations"})
        self.mock("get_all_roles", return_value=[{"role_id": 42}])
        self.mock("get_available_user_employees", return_value=[])
        self.mock("get_all_permissions", return_value=[{"permission_id": 5}])
        self.mock("generate_password_hash", return_value=SECRETS["password_hash"])
        self.super_admins = self.mock("count_active_super_admins", return_value=2)
        self.form = {**SECRETS, "confirm_password": SECRETS["password"], "username": "target.user", "role_id": "42", "permission_ids": "5"}
        self.auth_loader = self.mock("get_authorization_state")
        self.authenticate(case)

    def authenticate(self, case, *, logged_in=True, allowed=True):
        with self.client.session_transaction() as sess:
            sess.clear()
            if logged_in:
                state = user_state(permissions=[case.permission] if allowed else [])
                self.auth_loader.return_value = state
                stamp_session(self.erp.app, sess, state)
                sess.update(token=SECRETS["token"], session_secret=SECRETS["session_secret"])

    def assert_event(self, case, identifier=None):
        self.insert.assert_called_once()
        data = self.insert.call_args.kwargs
        self.assertEqual({key: data[key] for key in ("user_id", "username", "module", "action", "entity_type", "entity_id")}, {
            "user_id": 7, "username": "acting.user", "module": case.module, "action": case.action,
            "entity_type": case.entity, "entity_id": case.identifier if identifier is None else identifier,
        })
        for secret in SECRETS.values():
            self.assertNotIn(secret, repr(self.insert.call_args))

    def success(self, case):
        self.prepare(case)
        def audit_after_commit(**kwargs):
            self.assertEqual(self.commits, [case.operation])
        self.insert.side_effect = audit_after_commit
        response = self.client.post(case.path, data=self.form)
        self.assertEqual(response.status_code, 302)
        self.operation.assert_called_once()
        self.assert_event(case)
        if self.lookup:
            self.lookup.assert_called_once_with(42)
        if case.module != "PROCUREMENT":
            self.purchase.assert_not_called()

    def unauthorized(self, case):
        self.prepare(case)
        for logged_in in (False, True):
            self.authenticate(case, logged_in=logged_in, allowed=False)
            response = self.client.post(case.path, data=self.form)
            self.assertEqual(response.status_code, 302)
            self.operation.assert_not_called()
            self.insert.assert_not_called()
            if self.lookup:
                self.lookup.assert_not_called()

    def business_failure(self, case):
        self.prepare(case)
        # Validation exceptions and database/commit exceptions must precede audits.
        for error in (ValueError("Invalid business state"), RuntimeError("Commit failed")):
            self.operation.side_effect = error
            try:
                response = self.client.post(case.path, data=self.form)
                self.assertIn(response.status_code, (200, 302))
            except (ValueError, RuntimeError) as raised:
                self.assertIs(raised, error)
            self.insert.assert_not_called()
            self.assertEqual(self.commits, [])
            if self.lookup:
                self.lookup.assert_not_called()
        if case.module == "PROCUREMENT":
            self.operation.side_effect = None
            self.operation.return_value = False
            self.assertEqual(self.client.post(case.path, data=self.form).status_code, 302)
            self.insert.assert_not_called()

    def audit_failure(self, case):
        self.prepare(case)
        self.insert.side_effect = RuntimeError("Audit storage unavailable")
        self.assertEqual(self.client.post(case.path, data=self.form).status_code, 302)
        self.assertEqual(self.commits, [case.operation])
        self.operation.assert_called_once()
        self.insert.assert_called_once()
        with self.client.session_transaction() as sess:
            self.assertTrue(any(category == "success" for category, _ in sess["_flashes"]))

    def repository_transaction(self, case):
        """Run the real write repository and audit repository on separate fake DBs."""
        self.prepare(case)
        repository_name = {
            "PAYROLL": "payroll_workflow_repository", "LEAVE": "leave_repository",
            "PROCUREMENT": "purchase_request_repository", "FINANCE": "expense_repository",
            "ADMINISTRATION": "user_repository",
        }[case.module]
        repository = importlib.import_module(repository_name)
        business = Mock(name="business_connection")
        cursor = business.cursor.return_value
        cursor.rowcount = 1
        cursor.lastrowid = 42
        before_status = {
            "payroll_submit": "DRAFT", "payroll_return": "PROCESSING",
            "payroll_approve": "PROCESSING", "payroll_paid": "APPROVED",
            "expense_approve": "DRAFT", "expense_paid": "APPROVED",
        }.get(case.name, "PENDING")
        row = {
            "status": before_status, "period_number": "PAY-0042", "request_number": "LV-0042",
            "start_date": date(2026, 1, 1), "end_date": date(2026, 1, 1),
            "annual_entitlement": None, "employee_id": 9, "leave_name": "Annual",
        }

        def reset_rows():
            if case.name == "leave_approve":
                cursor.fetchone.side_effect = [row, None, None]
            elif case.name == "payroll_paid":
                cursor.fetchone.side_effect = [row, {"total_entries": 1, "approved_entries": 1}]
            else:
                cursor.fetchone.side_effect = None
                cursor.fetchone.return_value = row

        self.stack.enter_context(patch.object(repository, "get_connection", return_value=business))
        if case.module == "PAYROLL":
            self.stack.enter_context(patch.object(repository, "_validate_payroll_ready", return_value={"total_entries": 1}))
        self.operation.side_effect = getattr(repository, case.operation)
        audit_repository = importlib.import_module("audit_log_repository")
        audit = Mock(name="audit_connection")
        self.stack.enter_context(patch.object(audit_repository, "get_connection", return_value=audit))

        def write_audit(**kwargs):
            business.commit.assert_called_once()
            business.rollback.assert_not_called()
            return audit_repository.create_audit_log(**kwargs)

        self.insert.side_effect = write_audit
        for audit_broken in (False, True):
            with self.subTest(audit_broken=audit_broken):
                business.reset_mock()
                audit.reset_mock()
                self.insert.reset_mock()
                reset_rows()
                audit.cursor.return_value.execute.side_effect = RuntimeError("Audit insert failed") if audit_broken else None
                self.assertEqual(self.client.post(case.path, data=self.form).status_code, 302)
                self.assert_event(case)
                business.commit.assert_called_once()
                business.rollback.assert_not_called()
                business.close.assert_called_once()
                cursor.close.assert_called_once()
                if audit_broken:
                    audit.commit.assert_not_called()
                    audit.rollback.assert_called_once()
                else:
                    audit.commit.assert_called_once()
                    audit.rollback.assert_not_called()
                audit.close.assert_called_once()

        # A failed real business commit rolls back and never reaches the audit DB.
        business.reset_mock()
        audit.reset_mock()
        self.insert.reset_mock()
        reset_rows()
        business.commit.side_effect = RuntimeError("Business commit failed")
        with self.assertRaisesRegex(RuntimeError, "Business commit failed"):
            self.client.post(case.path, data=self.form)
        business.rollback.assert_called_once()
        self.insert.assert_not_called()
        audit.cursor.assert_not_called()

        # Repeating a completed workflow transition is rejected by the repository.
        if case.module in {"PAYROLL", "LEAVE", "PROCUREMENT", "FINANCE"}:
            business.reset_mock()
            business.commit.side_effect = None
            cursor.rowcount = 0
            cursor.fetchone.side_effect = None
            cursor.fetchone.return_value = {**row, "status": "COMPLETED"}
            self.assertEqual(self.client.post(case.path, data=self.form).status_code, 302)
            self.insert.assert_not_called()
            audit.cursor.assert_not_called()

    def lookup_failure(self, case):
        self.prepare(case)
        for result in (None, {}, {case.key: None}, RuntimeError("Lookup unavailable")):
            self.insert.reset_mock()
            self.operation.reset_mock()
            self.commits.clear()
            self.lookup.side_effect = result if isinstance(result, Exception) else None
            self.lookup.return_value = result
            self.assertEqual(self.client.post(case.path, data=self.form).status_code, 302)
            self.assert_event(case, identifier=42)

    def test_route_validation_blocks_audits(self):
        cases = {case.name: case for case in ACTIONS}
        scenarios = [
            ("user_create", {"password": "short"}),
            ("user_create", {"confirm_password": "mismatch"}),
            ("user_create", {"role_id": "999"}),
            ("password_reset", {"confirm_password": "mismatch"}),
            ("leave_reject", {"rejection_reason": ""}),
            ("leave_reject", {"rejection_reason": "x" * 501}),
            ("purchase_reject", {"rejection_reason": ""}),
            ("role_permissions", {"permission_ids": "invalid"}),
            ("role_permissions", {"permission_ids": "999"}),
        ]
        for name, overrides in scenarios:
            with self.subTest(name=name, overrides=overrides), ExitStack() as local:
                # Each scenario needs an independent set of patches.
                old = self.stack
                self.stack = local
                try:
                    case = cases[name]
                    self.prepare(case)
                    self.form.update(overrides)
                    self.assertIn(self.client.post(case.path, data=self.form).status_code, (200, 302))
                    self.operation.assert_not_called()
                    self.insert.assert_not_called()
                finally:
                    self.stack = old

    def test_budget_blocks_payment(self):
        case = next(c for c in ACTIONS if c.name == "expense_paid")
        self.prepare(case)
        for budget in ({"budget_required": True, "budget_found": False, "department_name": "Ops", "budget_year": 2026}, {"budget_required": False, "can_pay": False, "over_by": 10}):
            self.budget.return_value = budget
            self.assertEqual(self.client.post(case.path, data=self.form).status_code, 302)
            self.operation.assert_not_called()
            self.insert.assert_not_called()

    def test_protected_user_and_role_changes(self):
        case = next(c for c in ACTIONS if c.name == "user_deactivate")
        self.prepare(case)
        with self.client.session_transaction() as sess:
            state = user_state(user_id=42, permissions=[case.permission])
            self.auth_loader.return_value = state
            stamp_session(self.erp.app, sess, state)
        self.client.post(case.path, data=self.form)
        self.authenticate(case)
        self.user.return_value["role_name"] = "Super Admin"
        self.super_admins.return_value = 1
        self.client.post(case.path, data=self.form)
        self.operation.assert_not_called()
        self.insert.assert_not_called()
        case = next(c for c in ACTIONS if c.name == "role_permissions")
        self.authenticate(case)
        self.role.return_value["role_name"] = "Super Admin"
        update = self.mock("update_role_permissions")
        self.client.post(case.path, data=self.form)
        update.assert_not_called()
        self.insert.assert_not_called()

    def test_read_only_forms_do_not_audit(self):
        for case in ACTIONS:
            if case.name not in {"user_create", "password_reset", "purchase_reject", "role_permissions"}:
                continue
            with self.subTest(action=case.name), ExitStack() as local:
                old, self.stack = self.stack, local
                try:
                    self.prepare(case)
                    self.mock("get_role_permission_ids", return_value=set())
                    self.assertEqual(self.client.get(case.path).status_code, 200)
                    self.operation.assert_not_called()
                    self.insert.assert_not_called()
                finally:
                    self.stack = old


def install_action_tests():
    """Give every action/scenario its own test name and failure report."""
    scenarios = ("success", "unauthorized", "business_failure", "audit_failure", "repository_transaction")
    for case in ACTIONS:
        for scenario in (*scenarios, *(("lookup_failure",) if case.lookup else ())):
            def test(self, case=case, scenario=scenario):
                getattr(self, scenario)(case)
            setattr(BusinessAuditTests, f"test_{case.name}_{scenario}", test)


install_action_tests()


if __name__ == "__main__":
    unittest.main()
