# ERP v1 cleanup and hardening report

## Outcome

**BLOCKED for release acceptance: audit and safe cleanup completed, with an
unresolved pre-existing P1 Payroll freshness defect.** This is Assignment 2,
not production certification or Assignment 3. No push, merge, deployment,
company-data access, permission changes or production migrations occurred.

Six concrete findings were recorded: three P1 and three P2. Five were addressed
(two P1 and three P2); one P1 remains reproducible. Policy questions and
unqualified deployment/performance checks are tracked separately below.
No introduced P0/P1 regression was found in the executed checks. Passing the
ordinary regression suites does not waive the failing freshness audit gate.

## Baseline and prerequisites

Fetched origin and verified PR #29 merged at 2026-10-23 03:53:19 UTC:
`ee7e49b061a43891d9593f251fcf868004e85e2d`. Its ancestry includes GUI completion
`1f8d47c4dcd4a5549dfd748a5c7aa33bf44eea5c`.
GitHub ERP CI run 39892236332 completed successfully in all three jobs:
Python unit tests and syntax, JavaScript tests and syntax, Disposable MySQL
integration. The initial working tree was clean; GUI documentation and templates
were present. Created `feat/erp-v1-final-cleanup` from that verified origin/main.
Existing branches/commits, including paused HR/Payroll work, were preserved.

## Findings and repairs

| ID | Severity | Evidence / root cause | Disposition |
| --- | --- | --- | --- |
| C-01 | P1 | Receiving retried errno 1205/1213 even when raised by COMMIT or failed ROLLBACK. Actual transaction fault tests opened three connections instead of one. | Fixed. Only pre-commit lock failures with confirmed rollback produce an internal retry marker. Same UUID/payload and bounded retry remain. Commit/cleanup failures never authorize replay. |
| C-02 | P2 | Supplier native email controls rejected nonempty historical contact text accepted by the documented backend contract. New test failed on input type email. | Fixed using text inputs on Add/Edit. Optionality, 150-character limit, escaping and backend checks remain. Native submissions and persisted legacy text verified. |
| C-03 | P1 | Two disposable Payroll creates both passed overlap preflight and committed overlapping active periods (returned IDs 2 and 1). Overlap validation and write were separate transactions. | Fixed. Creates/edits lock existing payroll.process permission row, perform current overlap read and write in one transaction. No grants added. Late conflicts return 409; unavailable guard/storage returns 503. Submitted values remain escaped and recoverable. |
| C-04 | P2 | Cursor allocation/close fault in login lookup or request authorization skipped connection.close. Reproduction showed zero closes. | Fixed with protected cursor setup and nested cleanup. SQL, exception propagation, credentials and authorization semantics unchanged. |
| C-05 | P1 | Real monthly calculation followed by real same-second PRESENT to ABSENT attendance edit is accepted for submission without recalculation. Mainline compares updated_at > calculated_at; equal timestamps miss the changed source. | **Unresolved release blocker.** Explicit disposable audit exits 1. Stop freshness workstream pending reviewed coordinated source-evidence/schema integration and legacy-run policy; do not merge paused branch automatically. |
| C-06 | P2 | Historical Security reviews describe subsequently fixed IT write authorization and Procurement navigation issues as current; testing guide had stale suite count, MySQL timeout and first-hosted-run wording. | Corrected with explicit historical supersession notes and accurate CI/audit-gate instructions. Historical results remain labelled historical. |

C-01 changes no receiving SQL, balances, eligibility or history. Its real-commit
faults with error numbers 2013/1205/1213 now make exactly one automatic commit
attempt; an explicit same-UUID reconciliation finds exactly one saved delivery.

C-03 enforces the already-existing inclusive nonoverlap rule, rather than adding
a cutoff policy. Cancelled periods do not block ranges, adjacent dates remain
valid, the edited row is excluded, and PAID/non-DRAFT updates remain blocked.
Lock order is schedule gate then period reads/writes. Other mainline Payroll
workflows take period locks and do not acquire this gate in reverse order.
The gate serializes unrelated schedule edits; production throughput is unmeasured.
It does **not** coordinate Attendance/Leave or solve C-05. External SQL, legacy
workers, concurrent privileged DDL and deletion of the guard permission remain
outside application-only guarantees. Missing guard/storage fails closed.

## Module-by-module audit

Read actual Flask route/decorator inventories, the function inventory of all
26 repository files, dynamic SQL construction sites, schema/migration definitions,
validation, security and export helpers, relevant templates/navigation/CSS/JS,
CI/deployment instructions and prior reliability reports. Focused source review
followed sensitive write paths and known deferred questions. This is not a claim
of exhaustive path coverage or formal verification.

| Module | Concrete review / executed evidence | Assessment and remaining gap |
| --- | --- | --- |
| Authentication / sessions | Login, credential marker, request-local loader, disabled/changed-role checks, idle/absolute expiry, POST logout and same-session signed CSRF recovery; session/security/CSRF Python tests, security MySQL and Chrome workflows | C-04 fixed. Denied writes fail closed. Copied signed cookies lack per-device server revocation; production TLS/proxy and rate-limit controls unverified. |
| Administration / audit | users.manage guardian lock, last active Super Admin, self-role/status denial, protected Super Admin grants, role permission validation, audit payloads/viewer filtering; admin-integrity, audit-reading and audit smoke suites | Existing guards pass. Best-effort post-commit audit can be lost after a business commit; durable outbox is outside approved scope. No grants changed by this task. |
| Procurement | Supplier optional fields, PR draft/item parent locks, status transitions, PO duplicate/active supplier locks, receiving UUID/rollback/current-read and cancellation ordering; Supplier, PO eligibility, Procurement and receiving suites; Supplier/security Chrome | C-01/C-02 fixed. Own-request approval remains permitted by existing contract; owner decision D-01 below. Historical supplier references preserved. |
| Inventory | Category/item/warehouse eligibility and status targets, inactive historical assignment retention, stock balance/UUID locks, movements and read-only reconciliation snapshots; category/item/master/reporting/stock/warehouse suites | No stock calculation/history changes. Unit edits use live master labels and do not convert quantities; owner decision D-02 remains. |
| Finance | Exact Decimal bounds, reference locks, expense status transitions, expense then annual-budget lock with post-wait READ COMMITTED spending read, budgets/reports/export text typing; Finance audit/payment/reporting/validation, categories and budgets suites | Existing same-budget concurrent-payment and rollback checks pass. Budget reductions/reassignment and departmentless expenses remain allowed policy. Production search/export capacity unverified. |
| HR | Department/Employee revisions, strict validation, stale conflicts, Attendance uniqueness/date/time and Leave employee serialization/calendar-day rules; employee/HR audit/revision/validation, Attendance and Leave suites | No lifecycle integration or employment/account coupling added. Later Attendance changes to approved Leave require owner reconciliation policy. |
| Payroll | Mainline compensation/generation snapshots and effective-date selection, period scheduling, monthly weekday/half-month calculation, adjustments, submit/approve/pay and paid-only payslips; audit/security suites plus new schedule unit/MySQL/Chrome tests | C-03 fixed, C-05 blocks release. Do not equate tested transitions with certified salary output. Paused freshness/certification/monetary/lifecycle designs were read only, never integrated. D-03 remains. |
| IT Assets / Help Desk | Separate view/manage authorization, active references, custody/lost/maintenance/retirement guards, transactional ticket history and transitions, reports/XLSX; six Asset/authorization and Help Desk suites plus composed Chrome security workflows | Previously documented view-authorized writes are fixed in merged mainline. Current permission denials/revocation and historical/custody checks pass. Self-service/assignee-only policy is not inferred. |
| Shared infrastructure / deployment | Schema capability lease and admission order, explicit migrations, parameterized values and allowlisted dynamic SQL, export string handling, no unsafe template filters/DOM sinks found, static links and navigation, pinned CI tooling | 232 constant template url_for references resolve. No tracked .env. Schema gate/CI do not certify company schema, backups, restore, HTTPS, proxy, capacity or unknown external writers. |

Existing reports were assessed against actual mainline: IT authorization and
Procurement navigation are resolved; receiving/stock UUID, supplier eligibility,
HR revisions and budget-payment atomicity have current integration evidence.
Historical test totals in earlier reports are not re-labelled as new results.

## Unresolved decisions and limitations

| ID / severity | Evidence and consequence | Required next action |
| --- | --- | --- |
| C-05 / P1 blocker | Same-second source edit probe fails; timestamps are not sufficient evidence. Period date changes, source removals/Leave changes and validation-to-commit races also need coordinated freshness analysis. Only the same-second case is newly reproduced here. | Owner approves a scoped freshness integration/legacy-run plan, then implement/test on a separate reviewed branch. Preserve PAID history, do not attest old runs or automatically replay uncertain commits. Existing paused code is design evidence, not merged verification. |
| D-01 / P2 security-policy decision | PR creator (stored as requested_by) can submit/approve their own request if granted both permissions. Procurement fixture creates as user 1 and approves as user 1. Reject likewise lacks creator separation; repository rejection currently receives no actor argument. | **Awaiting project-owner approval.** Recommend creator cannot approve or reject, including Super Admin. Require a second authorized approver and define emergency/bootstrap operations. Enforce under repository transaction/current row plus route/UI feedback; pass actor into rejection; test self/other, Super Admin, CSRF, revocation, races, no unauthorized mutation/audit. Existing grants and saved historical approvals stay unchanged. |
| D-02 / P2 inventory-policy decision | Item UOM edits remain allowed; historical movements/reports join current item UOM and warehouse labels. Numeric quantities/foreign keys remain unchanged. Deactivation with stock remains permitted; manual stock needs active records. | **Awaiting owner approval.** Decide post-movement UOM freeze versus explicit version/conversion process, historical display semantics, inactive-item receiving and stock-clearance exceptions. No automatic conversion, recalculation or retroactive history restriction. |
| D-03 / P1 release acceptance decision | Current monthly engine uses 50% monthly basic pay and Monday-Friday dates; arbitrary period ranges are accepted, DAILY/HOURLY calculation is not implemented. Lifecycle/certified employment coverage is absent from mainline. Paused Payroll docs identify unresolved cutoffs, proration, calendar/rounding, roster/snapshot and approved-run recovery rules. | **Awaiting owner approval before salary-finalization certification.** Define supported v1 pay types/cutoffs and employment/leave/attendance evidence; explicitly exclude unsupported cases or approve a reviewed implementation. No payroll policy invented here and no paused branch merged. |
| L-01 / P2 technical debt | Static cursor-before-try candidates remain in older repository methods. Candidate count is not a confirmed leak count; this pass reproduces/fixes the authentication hot paths and protects changed writers. | Incremental fault-injection/cleanup work per repository, with transaction/uncertain-commit tests; avoid blanket rewrites. Not a newly demonstrated P1. |
| L-02 / P2 architecture limitation | Central audit is best effort after commit; signed cookies lack per-device revocation; stale nonrevision forms can overwrite edits. | Owner prioritizes durable audit/session/revision projects separately. Never infer rollback from a missing audit row. |
| L-03 / unverified deployment gate | No company DB inspected, production migrations/backups/restore, real HTTPS cookies/proxy, physical devices, manual screen readers, other browsers or production-scale load measured. | Separate authorized staging/deployment checks in Assignment 3 after review; do not treat GUI/test completion as production readiness. |

No P0 was identified in the reviewed/executed scope. D-01/D-02 are pending policy,
not silently activated restrictions. D-03 is a separate release acceptance gate;
it is not counted as a newly reproduced implementation defect.

## Verification commands and actual outcomes

Commands run from repository root using `.venv/Scripts/python.exe` (Python 3.14),
Node and MySQL Community Server 8.0.46. All MySQL data was synthetic on the
held-child, --no-defaults, dynamic-loopback, datadir/PID-verified harness.

| Command | Actual outcome |
| --- | --- |
| python -B -m unittest discover -s tests -q | **532 passed**, 12.781 seconds; expected fault-injection log messages are not suite failures |
| node --test tests/horizontal_navigation.test.cjs | **11 passed** |
| python -m pip check | Passed, no broken requirements |
| python -B -m unittest discover -s tests -p test_receiving_safety.py -q | 10 passed after two reproduced retry failures |
| python -B -m unittest discover -s tests -p test_procurement_audit.py -q | 7 passed |
| python -B -m unittest discover -s tests -p test_supplier_management.py -q | 15 passed after reproduced email control failure |
| python -B -m unittest discover -s tests -p test_payroll_schedule.py -q | 5 passed; initial new-fixture/value-retention failures corrected |
| python -B -m unittest discover -s tests -p test_auth_connection_cleanup.py -q | 3 passed after two reproduced cleanup failures |
| python -B -m unittest discover -s tests -p test_session_security.py -q | 19 passed |
| python -u -B tests/mysql_receiving_smoke.py | Passed expanded uncertain-commit/race/rollback/CSRF/audit coverage |
| python -u -B tests/mysql_payroll_schedule_smoke.py | Passed actual observed permissions-row lock wait, concurrent creates/edits, RR/RC, inclusive/adjacent/cancelled/paid/missing-gate cases |
| Remaining pre-existing mysql_*_smoke.py launchers, sequentially (each --mysqld verified binary) | **34/34 passed**; combined with receiving and new schedule suite, **36/36 applicable smoke suites passed** |
| python -u -B tests/mysql_supplier_management_browser.py | Final composed Chrome security/IT/Supplier workflow passed, including persisted legacy email assertion |
| python -u -B tests/mysql_payroll_schedule_browser.py | Composed Chrome security/IT and Payroll late conflict/native correction/reader workflow passed |
| python -u -B tests/mysql_payroll_freshness_audit.py | **FAIL, exit 1: C-05 P1 release blocker**; actual calculation and Attendance mutation, not mocked source data |
| python -B scripts/ci_checks.py python | Passed: 174 Python files, 110 Jinja templates |
| python -B scripts/ci_checks.py javascript | Passed: 28 JavaScript files |
| git diff --check origin/main | Passed, cumulative whitespace check |

The batch discovered 34 remaining existing suites before the new schedule file
was added; it deliberately excluded the already-successful receiving suite.
Equivalent complete smoke reproduction is `python -B scripts/ci_checks.py mysql`;
it was not rerun redundantly after all individual suites passed.
The separate freshness audit must also run: it is intentionally a failing
release gate, not a claim that 36 smoke passes establish freshness.

All 34 batch suite names:

```text
mysql_admin_integrity_smoke.py
mysql_attendance_smoke.py
mysql_audit_log_reading_smoke.py
mysql_audit_smoke.py
mysql_budget_management_smoke.py
mysql_dashboard_reliability_smoke.py
mysql_employee_listing_smoke.py
mysql_expense_category_management_smoke.py
mysql_finance_audit_smoke.py
mysql_finance_payment_smoke.py
mysql_finance_reporting_smoke.py
mysql_finance_validation_smoke.py
mysql_helpdesk_smoke.py
mysql_hr_audit_smoke.py
mysql_hr_revision_smoke.py
mysql_hr_validation_smoke.py
mysql_inventory_categories_smoke.py
mysql_inventory_items_smoke.py
mysql_inventory_master_smoke.py
mysql_inventory_reporting_smoke.py
mysql_it_asset_audit_smoke.py
mysql_it_asset_category_validation_smoke.py
mysql_it_asset_lifecycle_smoke.py
mysql_it_asset_reporting_smoke.py
mysql_it_asset_validation_smoke.py
mysql_it_authorization_smoke.py
mysql_leave_smoke.py
mysql_po_supplier_eligibility_smoke.py
mysql_procurement_smoke.py
mysql_schema_compatibility_smoke.py
mysql_security_smoke.py
mysql_stock_smoke.py
mysql_supplier_management_smoke.py
mysql_warehouse_smoke.py
```

Chrome 155.0.8059.85 checks exercised manager, read-only, IT Manager and Super Admin,
authentication/CSRF recovery, native values/escaping, authorization revocation,
denied business/history snapshots and valid persistence. These are affected
workflow checks, not fresh responsive-viewport or physical-device certification.
Relevant approver transitions use real authorized/denied Flask/MySQL audit suites;
no new manual approver-browser claim. Assignment 1's viewport evidence is historical.
Initial sandbox Chrome startup failed (ECONNRESET/locked Crashpad cleanup);
outside-sandbox isolated rerun and final runs passed. No browser security control
was disabled. A diagnostic lock-wait filter initially missed the waiting query;
the final assertion observes actual performance_schema lock waits on permissions.

Logs retained locally under %TEMP%: erp_cleanup_unittest.log, erp_cleanup_mysql.log,
erp_cleanup_receiving.log, erp_cleanup_supplier_before/after.log,
erp_cleanup_supplier_browser_final.log, erp_cleanup_payroll_before.log,
erp_cleanup_payroll_unit.log, erp_cleanup_payroll_schedule_final.log,
erp_cleanup_payroll_browser.log and erp_cleanup_payroll_freshness.log.
Logs are supporting workstation evidence, not committed company data.

## Exact changes and local commits

1. `5c523a1a7164c2d0a688a3c6a9a62ec5a40a6871` - receiving retry/cleanup repair and regressions; initial progress checkpoint.
2. `8b529d472c02e797eb9bdb32d25614a80c3b2764` - Supplier email contract correction and unit/native persistence tests.
3. `d2893958facc0dd5e3849a09265943ce743fc876` - atomic Payroll schedule guard, late conflict retention and unit/MySQL/Chrome tests.
4. `9ddf30fab297f2b7127f418a80819d5fa42d828e` - authentication connection cleanup and fault regressions.
5. Final audit/documentation checkpoint contains this report, explicit failing
   freshness probe, documentation corrections and final progress. Its SHA is
   provided in the final delivery; `git log origin/main..HEAD` lists exact commits.

Exact cumulative changed-file manifest (24):

```text
ERP_V1_CLEANUP_PROGRESS.md
ERP_V1_CLEANUP_REPORT.md
MERGE_SECURITY_REVIEW.md
SECURITY_REVIEW.md
SUPPLIER_MANAGEMENT.md
app.py
goods_receipt_repository.py
payroll_period_repository.py
templates/payroll/periods/add.html
templates/procurement/suppliers/add.html
templates/procurement/suppliers/edit.html
tests/README.md
tests/browser_payroll_schedule.cjs
tests/browser_supplier_management.cjs
tests/mysql_payroll_freshness_audit.py
tests/mysql_payroll_schedule_browser.py
tests/mysql_payroll_schedule_smoke.py
tests/mysql_receiving_smoke.py
tests/mysql_supplier_management_browser.py
tests/test_auth_connection_cleanup.py
tests/test_payroll_schedule.py
tests/test_receiving_safety.py
tests/test_supplier_management.py
user_repository.py
```

No database/schema/migration, role seed, requirements, CSS, application JavaScript
or unrelated GUI work changed. The only new permission-row use is locking an
existing definition for scheduling; no permission/grant insertion in production.
Synthetic fixtures alone contain test permissions/accounts/data.

## Review and Assignment 3 recommendation

Keep the four repairs as separate logical commits in a cleanup review PR, with
this audit checkpoint making C-05 and D-03 explicit. Do not publish until human
review authorizes it. Handle freshness/policy integration in a separately scoped
review; do not auto-merge paused HR/Payroll work. Assignment 3 must independently
rerun the failing freshness gate after a fix, test same-second/source-removal/
date-edit/Leave and validation-to-commit races, review legacy APPROVED-run
handling, supported salary policy and external-writer coordination, then assess
deployment/restore/capacity separately. Assignment 2 is **not unconditionally
complete and does not approve a v1 release**.
