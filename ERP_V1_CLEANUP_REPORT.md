# ERP v1 cleanup and hardening report

## Final publication review - 2026-10-23

Reviewed the eight original cleanup/freshness commits in their exact order against
origin/main ee7e49b061a43891d9593f251fcf868004e85e2d, including merged GUI completion
1f8d47c4dcd4a5549dfd748a5c7aa33bf44eea5c. No significant security, Payroll integrity
or migration compatibility blocker was found in the reviewed scope. The initial
working tree was clean. A separate documentation-only review commit corrects stale
security summaries, records the cumulative scope and clarifies application-wide
schema unavailability; the final publication therefore contains nine commits.

Actual cumulative scope is **48 changed files against origin/main**. The earlier
29-file manifest describes only the freshness continuation after 27bf6cf; it is
not the cumulative Assignment 2 count. All 48 files were reviewed and are cleanup
repairs, approved Payroll integration, focused tests or documentation.

Previously passing results were checked against the available actual logs and
assertions: 543 Python tests, 11 navigation tests, 38 smoke suites, unchanged C-05
probe, 15 scenarios, sixteen RR/RC ordered races, fault tests and affected Chrome
workflows. No runtime change was needed and successful expensive suites were not
rerun for this documentation-only review. Whitespace and manifest/ancestry checks
are repeated before publication. Disposable isolation verifies loopback, actual
server datadir and held-child PID; migration tests build legacy schemas without
freshness structures and preserve old columns/values before repeated upgrades.

Deployment remains unapproved. Drain every participating writer; verify backups,
target/version/engines and additive migration 010; deploy all new workers together;
verify schema admission before resuming writes. Missing/incompatible structures
can block application-wide database-backed requests, including login. DDL commits
implicitly; partial upgrades require operator inspection, and reverting to old
writers forfeits the integrity guarantee. No company data or production migration
was used in this review. APPROVED recovery remains a proposal, with no bypass or
automatic reopening. PAID history and Payroll arithmetic are preserved.

Outstanding owner decisions remain D-01 Purchase Request self-approval, D-02
historical UOM semantics/conversion restrictions, D-03 salary/cutoff/lifecycle
certification, APPROVED/PAID recovery and production rollout. Physical devices,
manual screen readers, other browsers, production TLS/proxy/restore and capacity
remain unverified. Publication authorizes only the feature branch for manual PR
review; it does not authorize production readiness, PR creation/merge or Assignment 3.

Reviewed original eight full SHAs, in order:

- 5c523a1a7164c2d0a688a3c6a9a62ec5a40a6871 Prevent automatic receiving retries after uncertain commit or rollback
- 8b529d472c02e797eb9bdb32d25614a80c3b2764 Align Supplier email forms with historical validation contract
- d2893958facc0dd5e3849a09265943ce743fc876 Enforce existing Payroll period nonoverlap inside write transactions
- 9ddf30fab297f2b7127f418a80819d5fa42d828e Close authentication connections when cursor setup or cleanup fails
- 27bf6cf06aadd8e3943892d049ffbc42cb70d7f7 Record ERP v1 audit results and unresolved Payroll freshness release gate
- 7cac7b2bc124e313fd900b2fad72697349530723 Persist and enforce scoped Payroll Attendance freshness
- a2824b231607cfa4cc40eac91225fa32ac36b5ef Verify Payroll freshness migrations, races and Chrome workflows
- 5ddab3bfb3124c08984f60ea8838134aeddf3637 Document verified Payroll freshness and rollout approval limits

Cumulative changed-file manifest:

- `ERP_V1_CLEANUP_PROGRESS.md`
- `ERP_V1_CLEANUP_REPORT.md`
- `MERGE_SECURITY_REVIEW.md`
- `PAYROLL_ATTENDANCE_FRESHNESS.md`
- `SECURITY_REVIEW.md`
- `SUPPLIER_MANAGEMENT.md`
- `app.py`
- `attendance_repository.py`
- `database/attendance_schema.sql`
- `database/core_schema.sql`
- `database/migrations/010_payroll_attendance_freshness.py`
- `database/migrations/README.md`
- `database/payroll_calculation_schema.sql`
- `goods_receipt_repository.py`
- `leave_repository.py`
- `payroll_adjustment_repository.py`
- `payroll_calculation_repository.py`
- `payroll_entry_repository.py`
- `payroll_freshness.py`
- `payroll_period_repository.py`
- `payroll_workflow_repository.py`
- `schema_compatibility.py`
- `templates/payroll/periods/add.html`
- `templates/procurement/suppliers/add.html`
- `templates/procurement/suppliers/edit.html`
- `tests/README.md`
- `tests/browser_payroll_freshness.cjs`
- `tests/browser_payroll_schedule.cjs`
- `tests/browser_supplier_management.cjs`
- `tests/mysql_audit_smoke.py`
- `tests/mysql_payroll_freshness_audit.py`
- `tests/mysql_payroll_freshness_browser.py`
- `tests/mysql_payroll_freshness_investigation.py`
- `tests/mysql_payroll_freshness_migration_smoke.py`
- `tests/mysql_payroll_freshness_smoke.py`
- `tests/mysql_payroll_schedule_browser.py`
- `tests/mysql_payroll_schedule_smoke.py`
- `tests/mysql_receiving_smoke.py`
- `tests/mysql_supplier_management_browser.py`
- `tests/test_attendance.py`
- `tests/test_auth_connection_cleanup.py`
- `tests/test_business_audit.py`
- `tests/test_leave.py`
- `tests/test_payroll_freshness.py`
- `tests/test_payroll_schedule.py`
- `tests/test_receiving_safety.py`
- `tests/test_supplier_management.py`
- `user_repository.py`


## Current approved implementation checkpoint ? 2026-10-23

C-05 is resolved in development: durable source generations, persisted calculation
scope/evidence and one transaction guard now protect calculation, submission,
approval and payment. Stale/unknown APPROVED payment rejects without reopening.
Original five cleanup commits remain unchanged. Assignment 2 is eligible for final
review after the checks recorded below; this is not publication or production
approval. Six findings (three P1/three P2) are addressed in development. D-03 salary
policy acceptance remains a separate production gate.

The implementation, migration contract, proven ordering, legacy handling and
proposed recovery are in [PAYROLL_ATTENDANCE_FRESHNESS.md](PAYROLL_ATTENDANCE_FRESHNESS.md).
No recovery workflow was implemented. Production migration/rollout, external-writer
coordination, guard throughput qualification, backup/rollback rehearsal and owner
approval of APPROVED/PAID correction policy remain outstanding. No push, merge,
deployment, company-data operations or Assignment 3 were performed.

Verified so far: unchanged original same-second audit PASS; all 15 investigation
scenarios PASS; sixteen source-first/Payroll-first races under both RR and RC PASS;
real lock timeouts/deadlocks, uncertain commits, missing/exhausted evidence and
Leave invalidation PASS. Migration legacy/partial/repeated/core-only/Attendance-only
checks PASS with amounts, statuses and old values preserved. Schema gate and audit
integration PASS. Full Python: 543 tests PASS; navigation: 11 PASS; dependency check
PASS. Syntax: 181 Python files, 110 Jinja templates and 29 JavaScript files PASS.
The Python run initially exposed outdated narrow audit mocks; those now isolate
the new boundary while retaining every commit/rollback/audit assertion. Dedicated
real MySQL and Chrome tests exercise the actual boundary without mocks.

Freshness Chrome PASS: manager/process and separate approver/pay roles, denied
reader, CSRF, native confirmations, stale submit/approve/pay, NULL legacy evidence,
explicit recalculation and successful fresh payment. No JS runtime exceptions.
Existing composed security and IT authorization workflows also PASS. Final
integration/browser totals are recorded in the completion checkpoint below.

## Approved continuation file manifest

29 files changed relative to preserved checkpoint 27bf6cf:

- `ERP_V1_CLEANUP_PROGRESS.md`
- `ERP_V1_CLEANUP_REPORT.md`
- `PAYROLL_ATTENDANCE_FRESHNESS.md`
- `attendance_repository.py`
- `database/attendance_schema.sql`
- `database/core_schema.sql`
- `database/migrations/010_payroll_attendance_freshness.py`
- `database/migrations/README.md`
- `database/payroll_calculation_schema.sql`
- `leave_repository.py`
- `payroll_adjustment_repository.py`
- `payroll_calculation_repository.py`
- `payroll_entry_repository.py`
- `payroll_freshness.py`
- `payroll_period_repository.py`
- `payroll_workflow_repository.py`
- `schema_compatibility.py`
- `tests/README.md`
- `tests/browser_payroll_freshness.cjs`
- `tests/mysql_audit_smoke.py`
- `tests/mysql_payroll_freshness_browser.py`
- `tests/mysql_payroll_freshness_investigation.py`
- `tests/mysql_payroll_freshness_migration_smoke.py`
- `tests/mysql_payroll_freshness_smoke.py`
- `tests/test_attendance.py`
- `tests/test_business_audit.py`
- `tests/test_leave.py`
- `tests/test_payroll_freshness.py`
- `tests/test_payroll_schedule.py`

## Completion checkpoint ? approved freshness implementation

C-05 development resolution is verified. Assignment 2 is ready for final review;
production readiness, publication and APPROVED recovery remain separately gated.
All five original cleanup commits are ancestors and unchanged.

New logical local commits:

- 7cac7b2bc124e313fd900b2fad72697349530723 ? runtime integrity, additive migration,
  fresh schemas, schema admission and focused unit/audit fixture updates (19 files).
- a2824b231607cfa4cc40eac91225fa32ac36b5ef ? actual MySQL migration/regression/race
  suites and Chrome workflow/security checks (5 files).
- Documentation commit follows these; its SHA is supplied in the final delivery.

Final verification (no skipped required checks):

| Check | Result | Local log / evidence |
| --- | --- | --- |
| Unchanged original audit | PASS, same-second stale submission rejected | %TEMP%/erp_freshness_original_final.log |
| All 15 scenarios + sixteen RR/RC races + fault/Leave extensions | PASS | %TEMP%/erp_freshness_verified.log |
| Migration legacy/partial/repeated/optional modules/incompatibility | PASS | %TEMP%/erp_freshness_migration_final.log |
| Schema compatibility gate | PASS | %TEMP%/erp_freshness_schema_gate.log |
| Cross-module transactional audit suite | PASS | %TEMP%/erp_freshness_audit_cross.log |
| Remaining MySQL suites | 34/34 PASS; combined smoke coverage 38/38 | %TEMP%/erp_freshness_mysql_remaining.log |
| Full Python | 543 PASS, 6.216 seconds | %TEMP%/erp_freshness_python_final.log |
| Navigation | 11 PASS, zero skipped | node --test tests/horizontal_navigation.test.cjs |
| Freshness Chrome | PASS roles, CSRF, confirmations, persisted outcomes | %TEMP%/erp_freshness_browser_final.log |
| Existing Attendance Chrome | PASS | %TEMP%/erp_freshness_attendance_browser.log |
| Existing Leave Chrome | PASS | %TEMP%/erp_freshness_leave_browser.log |
| Syntax | 181 Python, 110 Jinja, 29 JavaScript PASS | scripts/ci_checks.py python / javascript |
| Dependencies and whitespace | PASS | pip check; git diff --check origin/main |

All database checks used verified disposable MySQL and synthetic data only. The
full Python suite prints intentional fault-test exceptions and cleanup diagnostics;
its final result is OK, not a failed database run. The initial full-run audit-fixture
errors and first Chrome dialog-handling failure were corrected and their affected
checks rerun successfully. No previous failed attempt is counted as a pass.

Diff review confirmed unchanged calculation arithmetic, unchanged original audit,
no route/template/permission edits in this continuation, no business evidence
backfill and no company-data operations. The 29-file continuation manifest above
includes five documentation files. No expensive successful suites were repeated
for the final documentation update. No push/merge/deploy or Assignment 3.

## Historical audit and investigation record

Everything below records earlier checkpoints and proposals. Statements that C-05
is unimplemented, failing or awaiting development approval are historical and are
superseded by the current approved checkpoint above. Historical test counts are
not claims about the current implementation.


## Outcome

**BLOCKED for release acceptance: audit and safe cleanup completed, with an
unresolved pre-existing P1 Payroll freshness defect.** This is Assignment 2,
not production certification or Assignment 3. No push, merge, deployment,
company-data access, permission changes or production migrations occurred.

Blocker-resolution continuation: the unchanged original audit failed again.
An additional 15-scenario disposable investigation confirms gaps at submission,
approval and the validation-to-commit boundary. No application/schema fix has
been implemented. A concrete revision proposal and the required owner decisions
are below; approval is required before those changes, per section 5 of the
blocker-resolution assignment. The five existing commits remain unchanged.

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
5. `27bf6cf06aadd8e3943892d049ffbc42cb70d7f7` - original audit/documentation checkpoint and failing freshness probe.

The blocker-resolution continuation adds only an investigation script and updates
the two cleanup documents. These proposal/investigation changes are uncommitted;
there is no new freshness-fix commit.

Exact cumulative changed-file manifest including the continuation working tree (25):

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
tests/mysql_payroll_freshness_investigation.py
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

## Blocker-resolution investigation

### Current evidence

Baseline: clean feat/erp-v1-final-cleanup at 27bf6cf, exactly the five full SHAs
above; merged GUI commit ee7e49b and GUI head 1f8d47c are ancestors. Read calculation,
entry generation, workflow, period and adjustment repositories, Attendance writes,
the effective Leave approval writer, related Flask routes, schema/migration
definitions and test infrastructure. No paused branch was merged.

Commands actually run in this continuation:

- `python -u -B tests/mysql_payroll_freshness_audit.py`: **FAIL, exit 1**, unchanged
  assertion reproduces the original same-second defect.
- `python -u -B tests/mysql_payroll_freshness_investigation.py`: **exit 1,
  investigation completed with C-05 unresolved**. This is a diagnostic, not a
  passing regression suite. All 15 observations completed; both held-commit
  concurrency cases used actual repository transactions and bounded test events,
  not product sleeps. No application behavior or original failing probe changed.

| Scenario observed | Current result | Interpretation |
| --- | --- | --- |
| Same-second edit then submit | Accepted | Defect |
| Repeat submit while PROCESSING | Rejected | Existing status guard works |
| Change before explicit calculation | Accepted after calculation | Correct control |
| Multiple edits returning to original status | Accepted without recalculation | No durable change-generation evidence |
| Explicit recalculation after edit | Accepted | Correct recovery control |
| Ordinary later-second edit | Rejected | Existing greater-than timestamp check works in this limited case |
| Weekday row moved outside cutoff | Accepted | Old employee/date source disappears from join |
| Row reassigned to another employee | Accepted | Same missing-old-source gap |
| Replacement row inserted after reassignment | Accepted without recalculation | New same-second row evades timestamp check |
| Insert fills previously unrecorded day | Rejected until recalculation | Cached unrecorded_days guard works; not proof of general insertion freshness |
| DRAFT cutoff moved after calculation | Accepted with old calculation | Saved calculation lacks a durable period-scope binding |
| Edit after submission, then approve | Accepted | Approval repeats the same inadequate check |
| Later-second edit after approval, then pay | Accepted | Payment checks statuses/counts only; post-approval policy is not established |
| Attendance commits while submit is held after validation/before commit | Both commit | No writer coordination across validation and commit |
| Attendance commits while approval is held after validation/before commit | Both commit | Same transaction-consistency defect |

Logs: %TEMP%/erp_freshness_resolution_baseline.log and
%TEMP%/erp_freshness_resolution_investigation.log. Both disposable servers shut
down and their temporary directories were removed. Fixture timestamps were fixed
only to reproduce collisions; later-second controls used a separate test session
timestamp. No company configuration/database was used.

### Complete lifecycle implications

Calculation locks the period/entries and reads Attendance/approved Leave under
locks, but stores only amounts/counters and a second-resolution calculated_at.
Those locks end at commit. Submission/approval do not retain a comparable source
version or coordinate with Attendance writers until commit. The stale query is
an inner join over current employee/date membership, so removals/reassignments
are invisible even independently of precision. A repeated submission is rejected
by status; that guard cannot validate the first stale submission.

Generation copies compensation fields and leaves calculation markers empty.
Period date edits currently retain old calculation markers/counters. Adjustment
writes refresh preview totals inside DRAFT; they must not mint attendance evidence.
Return-to-Draft does not itself prove freshness; explicit calculation must do so.
There is no application Attendance delete route/repository operation. Supported
create/edit can change employee and date. Effective Leave approval directly inserts
missing ON_LEAVE attendance and therefore is an Attendance writer too.

Approved-to-Paid performs no source-freshness check. There is no existing
APPROVED-to-DRAFT recovery route. Blocking stale/unverifiable approved runs or
treating approval as an immutable payment snapshot has operational/policy
consequences; neither is silently chosen here. Existing PAID amounts/statuses
must never be rewritten by this fix.

### Proposed approach: scoped durable generations and calculation snapshots

**Design proposal only. No DDL, migration file or production code is implemented.**
Recommend explicit monotonic employee/date generations and persisted daily
snapshots, plus a transaction coordination row. This avoids timestamp semantics,
content-hash collisions/ABA questions and invalidating an unrelated employee or
out-of-period day merely because a global generation changed.

Proposed additive schema:

1. InnoDB payroll_attendance_guard: singleton guard_id=1, primary key and enforced
   singleton CHECK. This row is locked, never used as a mutable freshness counter.
2. InnoDB payroll_attendance_generations: primary key (employee_id, attendance_date),
   generation signed BIGINT NOT NULL with enforced positive bound. Absence means
   generation zero. Rows are durable tombstones: never remove/reset/recycle them
   when an Attendance row moves or a future approved delete occurs.
3. InnoDB payroll_attendance_snapshots: primary key (payroll_entry_id,
   attendance_date), captured employee_id and generation (zero allowed). Entry FK
   preserves referential integrity; do not cascade away PAID evidence. One row for
   every scheduled weekday, including a missing Attendance day at generation zero.
4. Nullable metadata on payroll_entries: attendance_evidence_version SMALLINT
   UNSIGNED plus attendance_scope_start/end DATE. NULL means unknown/unverified,
   not fresh. A known version requires a complete matching daily snapshot set,
   captured employee identity and exact current period scope.

The narrow attendance generations should cover every accepted Attendance insert
or save, including date/employee moves. An accepted no-op save may conservatively
advance the generation and require recalculation; document this explicitly.
Increment the old and new keys on moves, once per distinct key in deterministic
order. Never infer an old key from submitted values: read the locked stored row.
This preserves detection across multiple edits and moves away/back, and catches
replacement insertions. No Attendance delete endpoint is added; any future
approved deletion must advance the old key and retain its tombstone.
Leave approval's direct attendance inserts must advance the same generations in
the same transaction. Counter exhaustion must fail closed before arithmetic,
never wrap/clamp/reset, including non-strict SQL mode.

During explicit calculation, acquire coordination, period and entry locks, read
current generation/source data, run the unchanged existing formula and save
amounts plus full snapshots/version/scope in the same transaction. Missing days
still use the existing unrecorded_days behavior. Calculation failure rolls back
both result and evidence. Only explicit successful calculation can create evidence.

Submission and approval acquire the same coordination first, validate current
period/entry statuses and exact saved scope, compare every expected weekday
generation/employee, and retain coordination through commit. Missing/unknown
version, incomplete snapshot, changed scope or generation rejects without
transition or success audit. Do not silently recalculate. A source writer that
commits first is observed; one that arrives after validation waits until the
transition commits, and its subsequent generation change makes later validation
stale. This linearization does not prohibit future HR edits or authorize payment
after them; payment behavior still requires the decision below.
Use current locking reads for sources/generations after any guard wait, not an
earlier REPEATABLE READ snapshot. Normalized daily rows are proposed instead of a
JSON blob so completeness, keys and generation comparisons remain directly
inspectable and testable; this trades extra rows for explicit scope integrity.

### Locking, scope and migration plan

Use one conservative guard initially to make lock order inspectable:
guard -> existing schedule permission gate (when needed) -> periods by ID ->
entries by ID -> existing source/reference locks -> generation keys sorted by
employee/date. All relevant Payroll mutators (generation, calculation, period
edit/cancel, adjustments, submit/return/approve and proposed payment validation)
must acquire the guard before their present locks. Attendance and effective Leave
approval take it before any employee/type/attendance locks. This also prevents
an adjustments entry-to-period lock order from interleaving with period-to-entry
calculation. Audit remains best effort after confirmed business commit.

Inspect all other Leave writers for a cycle before implementation. Source
classification changes (such as leave_types.is_paid for an already approved
ON_LEAVE interval) can change calculated pay without editing Attendance. This
narrow mechanism must not claim complete Leave/Payroll source certification.
Recommend a separately specified approved-Leave evidence component before
certifying full salary freshness; no Leave eligibility or formula is changed here.

Unrelated employees/dates share a short lock but do not invalidate each other's
evidence. The singleton serializes participating writers and may reduce throughput.
Generation rows grow by distinct edited employee/date; snapshots grow by entry
times scheduled weekdays. No retention purge or arbitrary cutoff limit is inferred;
measure real staging workloads separately. Direct privileged SQL, imports and old
workers bypassing coordination are outside its guarantee. Inventory external
writers and either adapt/fence them or refuse a freshness guarantee.

Proposed migration name: 010_payroll_attendance_freshness.py, subject to confirming
the reserved numbering of paused branches; do not create/reuse their 004-009 files.
It would use the explicit-target, password-prompt, no-dotenv/no-import-DDL pattern
of migration 008. Validate MySQL version, InnoDB, columns, full keys/CHECKs and
partial states; be repeatable without resetting counters/evidence.

- Existing Attendance rows need no pretend history backfill: generation zero is
  the baseline only for a *new explicit calculation*. Existing calculations keep
  NULL evidence. Never manufacture snapshots from today's Attendance to attest
  an older calculation.
- Existing DRAFT/PROCESSING runs need explicit calculate or return-to-Draft and
  calculate before transition. Preserve stored amounts/history until that user
  action; no bulk rewrite or automatic resubmission.
- Existing APPROVED runs need the explicit owner decision below. Preserve PAID
  rows unchanged and readable; no migration of salaries or status history.
- Fresh installations define guard/generations with Attendance and evidence
  tables/columns with Payroll calculation schema, in the documented install order.
  Attendance-only installations must not be forced to install optional Payroll
  business tables. Missing/partial required freshness structures fail closed for
  participating writes; update schema diagnostics and relevant admission checks,
  without a testing or legacy bypass.
- Deployment requires separate approval, restorable backup, drained writes across
  Attendance/Leave/Payroll and all workers, explicit migration, schema checks and
  coordinated new workers. No mixed-worker rollout. DDL implicitly commits;
  interrupted application requires inspected repeat/fix-forward, not assumed rollback.
- Retain additive schema on recovery. Old binaries cannot provide this guarantee
  and must not resume participating writes simply because columns remain. A code
  rollback without a reviewed source-writer/freshness plan is not safe.
- Lock timeout/deadlock: rollback, safe reload feedback and no success audit.
  Lost commit acknowledgment is uncertain: reconcile before explicit retry; no
  automatic replay, new evidence minting or counter compensation/reset.

### Alternatives rejected and approval boundary

Sleep/delay, greater-than-or-equal timestamp checks and microseconds alone do not
provide source identity/history or validation-to-commit protection. Locking only
existing Attendance rows misses moved/absent keys and future inserts. A hash of
current values without monotonic generations misses edit-and-revert history.
A global counter falsely invalidates unrelated cutoffs/employees. Reusing notes
or timestamps as an undocumented evidence-version field is not maintainable.
Simply clearing calculated_at in current writers cannot distinguish legacy
unverified calculations at cutover and still needs complete writer coordination.
No automatic recalculation, historical backfill or paused-branch merge is proposed.

Owner approval requested for this concrete scope before implementation:

1. Approve the additive generation/snapshot schema and coordinated writer rollout
   for this attendance invariant (development/disposable implementation only;
   company migration/deployment stays separately prohibited).
2. Approve fail-closed NULL/unknown evidence for legacy DRAFT/PROCESSING runs,
   requiring explicit user recalculation rather than synthesized backfill.
3. Decide APPROVED-to-Paid handling. **Recommend rejecting payment when evidence is
   stale or unknown, including legacy APPROVED runs, with no auto-reopen/reset.**
   This can strand approved runs because there is no approved recovery workflow.
   Define/approve a separate recovery procedure before operational use, or
   explicitly choose approval-as-payment-snapshot semantics. Do not infer an
   exception for Super Admin.

This approval boundary comes from the user's blocker-resolution assignment,
section 5: "If an explicit owner decision is required before implementing the
design, stop the affected implementation and present the proposal for approval."
Schema compatibility/legacy treatment and payment lifecycle are the concrete
decisions. This is not a request to access company data or deploy.

### Required verification after approval (not yet executed for a fix)

Keep the original audit assertion unchanged and require it to pass. Add exact
generation/snapshot and real-transaction tests for same/later-second changes,
changes before calculation, multiple edits/ABA, old/new employee/date keys,
replacement insertion, zero-generation absent days, out-of-scope stability,
explicit recalculation, period-scope changes and complete evidence validation.
Use actual lock waits and barriers in both winner orderings for calculation,
submit and approve versus Attendance/Leave writers under RR/RC; test rollback,
1205/1213, generation exhaustion, precommit and lost-ack faults, incomplete/
repeated migration and schema admission. Add payment/legacy cases only according
to the approved policy, preserving PAID history.

Run authorization/CSRF and denied-mutation/audit snapshots, relevant Payroll/HR/
Attendance/Leave/security suites, affected Chrome workflow/recovery checks, full
Python and JS/navigation, syntax/dependencies/whitespace and cumulative diff.
The previous 532/11/36 results above remain historical cleanup evidence, not
verification of this unimplemented proposal. No expensive full suite was repeated
for a production-code-free investigation.

Continuation changed files only: ERP_V1_CLEANUP_REPORT.md,
ERP_V1_CLEANUP_PROGRESS.md, tests/mysql_payroll_freshness_investigation.py.
No new fix commit, push, merge, migration or deployment. P0 identified: zero;
P1 implementation findings: two fixed, C-05 unresolved; P2 findings: three
addressed. D-03 salary policy and other owner decisions remain separate.
Assignment 2 is **not ready for final publication**.

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
