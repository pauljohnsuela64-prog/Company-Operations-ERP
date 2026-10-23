# ERP v1 release verification progress

Baseline: 4b927555c5e76aa236bf9924895daec4c27198df (merged PR #30).
Branch: feat/erp-v1-release-verification. Initial tree clean; prior branches preserved.
Implementation approval covered local synthetic verification only. Separate
feature-branch publication approval is recorded below; rollout remains unauthorized.

## Final publication review

The original four full commit SHAs and order, clean initial tree, merged PR #30,
origin/main baseline and exact 16-file scope were independently verified again.
All 13 recorded log hashes match their preserved artifacts; 544 Python, 11 navigation,
38 SQL suites, original freshness gate, migration/restore and final Chrome/Edge
results reconcile. Final syntax/dependency/whitespace checks passed. Expensive
successful suites were reused because reviewed test/application sources are unchanged.

One additional documentation-only commit corrects the Finance procedure name to
mysql_finance_payment_smoke, removes an unsupported Audit Logs export implication
and deduplicates a source reference. Actual executed evidence and readiness
classifications are unchanged. Final publication contains five commits and 16 files;
the original four commits remain unchanged. No runtime/schema/policy changes.

The latest authorization permits only feature-branch publication for manual PR
review. Earlier no-publication statements below describe the implementation-stage
checkpoint. No PR creation/merge, tag/release, deployment, company data operation
or production migration is authorized. Demo remains READY only for isolated synthetic
use; internal pilot and production remain NOT READY. All owner gates remain open.

## Checkpoint 1 - baseline and independent checks

- PASS: fetched origin/main; PR #30 merged; Assignment 1 and all nine Assignment 2
  commits are ancestors; merged tree equals reviewed cleanup tree.
- BLOCKED/PENDING: baseline ERP CI run 39917785782 was in progress at first check.
  Do not substitute prior PR checks for its final result.
- Independent Python/navigation/syntax and all 38 disposable MySQL suites started.
  Their results are NOT TESTED until completion is confirmed.
- Existing release/security/cleanup, freshness and deployment records are being
  reviewed. Historical counts are evidence leads, not final verification results.

## Verification matrix (initial state)

PASS, FAIL, BLOCKED, NOT TESTED and NOT APPLICABLE refer only to the described
procedure. A passing automated procedure does not certify all possible inputs.
Each final row will link actual evidence, permissions, sources and limitations.

| Group | Expected behavior and procedure | Sources | Required permissions | Initial status |
| --- | --- | --- | --- | --- |
| Authentication | Login/logout, expiry, credential invalidation, disabled users, revoked roles; security/session suites and native browser | security.py, csrf_security.py, user_repository.py, app.py | anonymous login; authenticated session | NOT TESTED |
| Administration | Account updates, last-admin safety, audit access and denied writes; admin/audit suites | user_repository.py, audit_log_repository.py | users.manage, roles.manage, audit_logs.view | NOT TESTED |
| Procurement | Supplier/PR/items/submit/approve/reject/PO/partial/full receiving; rollback and uncertain commit suites | supplier_repository.py, purchase_request_repository.py, purchase_order_repository.py, goods_receipt_repository.py | suppliers/requests/orders/receipts permissions per route inventory | NOT TESTED |
| Inventory | Masters/warehouse eligibility, stock IN/OUT, concurrent UUID operations, movement/reconciliation/reports and history | inventory_item_repository.py, stock_repository.py, warehouse_repository.py | inventory view/manage/write permissions per route inventory | NOT TESTED |
| Finance | Expense/budget approval/payment, exact precision, concurrent budget limits, exports and audit | expense_repository.py, budget_repository.py, finance_export.py | finance view/manage/approve/pay/budgets permissions per route inventory | NOT TESTED |
| HR | Departments/employees/revisions, Attendance, Leave approval/balance, reporting and history | department_repository.py, employee_repository.py, attendance_repository.py, leave_repository.py | HR and Attendance/Leave permissions per route inventory | NOT TESTED |
| Payroll | Scheduling, compensation/entries/adjustments, calculate/submit/return/approve/pay/payslip/report | payroll_*_repository.py | payroll.view/process/approve/pay | NOT TESTED |
| Freshness/migration | Original probe, 15 scenarios, 16 ordered races, legacy/partial migration, schema gate and backup/restore rehearsal | payroll_freshness.py, migration 010, schemas, schema_compatibility.py | existing Payroll/Attendance/Leave permissions; isolated operator for DDL | NOT TESTED |
| IT/Help Desk | Registration/custody/maintenance/lifecycle, ticket assign/resolve/close, history/reports and authorization | it_asset_repository.py, help_desk_repository.py | assets/helpdesk view/manage permissions per route inventory | NOT TESTED |
| GUI/accessibility | Five widths, roles, forms/tables/states/print/keyboard/focus/labels; browser checks | templates, style.css, navigation.js | manager/approver/reader/denied/anonymous | NOT TESTED |
| Reliability/capacity | Bounded synthetic timing, lock contention, connection cleanup, recovery | repositories and disposable harness | synthetic operator only | NOT TESTED |
| Deployment | Read config/docs; controlled checks only, no public deployment | security.py, database.py, .env.example, deployment docs | no company access | NOT TESTED |

Physical devices, human screen-reader testing and production operations are NOT
TESTED. Decisions on salary/lifecycle, APPROVED recovery, PAID corrections, PR
self-approval, UOM and migration rollout remain owner decisions, not implicit fixes.

## Resumable commands

Use .venv/Scripts/python.exe; never run connection-check or setup scripts against
workstation defaults. Current logs: %TEMP%/erp_release_python.log,
erp_release_navigation.log, erp_release_syntax.log and erp_release_mysql.log.
All SQL suites use the datadir/PID-verified disposable harness and synthetic data.


## Checkpoint 2 - CI, source contract and migration rehearsal

- PASS: baseline main-push run 39917785782 completed successfully in all three
  jobs (Python 120295412923, JavaScript 120295413186, MySQL 120295413697).
- PASS: merged-baseline full Python 543 tests (7.032 seconds), navigation 11,
  dependency consistency and baseline Python/Jinja/JavaScript syntax.
- Initial MySQL batch stopped at expense-category suite before business assertions:
  Windows denied its dynamically selected TCP port. Completed earlier suites remain
  valid; remaining suites are rerunning outside the sandbox with identical isolation.
- Confirmed release-verification defect RV-01: frozen GUI contracts still expected
  pre-cleanup Payroll blank controls and Supplier type=email. The approved behavior
  preserves submitted Payroll values and accepts historical Supplier contact text.
  Correct only those expectations; retain all other frozen route/CSRF/status/value
  contracts. Six focused schedule tests pass; affected browser reruns in progress.
- PASS new release rehearsal: real schema admission fresh/pre-010/post-010; no runtime
  repair; partial/repeated 010; legacy amounts/statuses preserved; exact backup and
  restore of 32 synthetic tables; restored stale rejection then explicit calculation,
  submit, approve and pay; prior PAID entry unchanged.
- Bounded timing: one employee/five weekdays/two periods, twenty serial calculations,
  median 37.715 ms, max 52.368 ms; twelve calculations/four workers 137.711 ms total.
  Other release checks were running concurrently. This is not production capacity.
- PASS additional Chrome AX/keyboard checks: 55 page-width cases, 407 named controls,
  main/heading semantics, actual Tab focus rings and no page-wide overflow.
- Edge and full visual/functional browser groups remain NOT TESTED until completion.
- Runtime application code remains unchanged. New tests and route-permission CSV
  cover only synthetic verification. All read-only policy/deployment gaps remain.


## Final workflow verification matrix

Results apply only to each described procedure. Exact routes and permission codes
are in docs/ERP_V1_ROUTE_PERMISSION_INVENTORY.csv (138 static declarations/38 codes).
Evidence root is %TEMP%; full paths and final attempts are in the test report.

| ID | Expected behavior | Sources | Required permissions | Procedure | Result | Evidence | Defects | Limits |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUTH-1 | Valid/invalid login, logout and old-tab rejection | security.py; app.py; user_repository.py | public login / authenticated session | mysql_security_smoke + composed native security browsers | PASS | SQL/security and all browser logs | No confirmed defect | No public TLS/MFA/rate limiter certification |
| AUTH-2 | Idle/absolute expiry, password/disabled-account invalidation and role changes | security.py; tests/test_session_security.py | current active user and route permission | full Python + mysql_security_smoke | PASS | erp_release_python_final.log; resume/mysql_security_smoke.py.log | None | In-flight requests are not retroactively revoked; copied-cookie limit |
| ADMIN-1 | Create/update users and roles; protect last Super Admin and denied operations | user_repository.py; app.py | users.manage; roles.manage | mysql_admin_integrity_smoke + browser | PASS | 38-suite evidence; browser batch | None | Company role acceptance not tested |
| ADMIN-2 | Authorized audit filters/pages, no private payload leakage | audit_log_repository.py; audit_log_validation.py | audit_logs.view | mysql_audit_smoke; mysql_audit_log_reading_smoke; native IT audit browser | PASS | 38-suite evidence; AX/GUI and IT compositions | None | Central audit remains best effort after commit |
| PROC-1 | Supplier create/edit/status; legacy text and optional values; historical references | supplier_repository.py; supplier_management.py | procurement.view; procurement.suppliers.manage | mysql_supplier_management_smoke + corrected tables/forms composition | PASS | erp_release_tables_isolated.log; SQL suffix | RV-01 test expectation corrected | No new email-format policy |
| PROC-2 | PR draft/items, submit, approve/reject and denied mutation | purchase_request_repository.py; app.py | procurement.requests.create/approve; procurement.view | mysql_procurement_smoke; GUI Procurement native workflow | PASS | SQL suffix; mysql_gui_procurement_browser.py.log | None | Self-approval remains existing contract, owner decision |
| PROC-3 | PO creation, active-supplier references and warehouse receiving eligibility | purchase_order_repository.py; goods_receipt_repository.py | procurement.orders.manage; procurement.receipts.manage | PO eligibility, warehouse and Procurement suites | PASS | 38-suite evidence; Procurement GUI persistence proof | None | External writers not certified |
| PROC-4 | Partial/full receiving, exact stock integration and duplicate UUID reconciliation | goods_receipt_repository.py; stock_repository.py | procurement.receipts.manage | mysql_receiving_smoke + GUI Procurement persisted proof | PASS | SQL suffix; Procurement browser log | None | Reconcile uncertain commit explicitly; do not replay blindly |
| INV-1 | Category/item creation/edit/status and reference/history eligibility | inventory_category_repository.py; inventory_item_repository.py | inventory.view; inventory.categories.manage; inventory.items.manage | category/item/master smoke + catalog browser | PASS | 38-suite evidence; catalog browser | None | UOM live-label semantics unchanged |
| INV-2 | Warehouse filters/forms/status, inactive historical assignments and races | warehouse_repository.py | inventory.view; inventory.warehouses.manage | mysql_warehouse_smoke; mysql_gui_warehouse_browser | PASS | SQL suffix; Warehouse browser | None | No history or eligibility policy changed |
| INV-3 | Stock IN/OUT exact decimals, concurrent withdrawals and UUID protection | stock_repository.py | inventory.view; inventory.stock.manage | mysql_stock_smoke | PASS | SQL suffix/mysql_stock_smoke.py.log | None | No production load capacity claim |
| INV-4 | Movements/reconciliation/reports/exports; no read-side stock changes | stock_repository.py | inventory.view | mysql_inventory_reporting_smoke; full GUI stock group | PASS | SQL suffix; erp_release_gui_v1_corrected.log | None | Large exports need capacity qualification |
| FIN-1 | Expense categories and draft/edit/approval/payment status rules | expense_category_repository.py; expense_repository.py | finance.view; finance.categories.manage; finance.expenses.manage/approve/pay | category, validation, audit, functional smoke + Finance browser | PASS | 38-suite evidence; finance functional browser | None | No inferred new approval policy |
| FIN-2 | Annual budget limits under concurrent payments, exact Decimal and rollback | budget_repository.py; expense_repository.py | finance.view; finance.expenses.manage/pay | mysql_budget_management_smoke; mysql_finance_payment_smoke | PASS | 38-suite evidence | None | Departmentless/reassignment policy remains existing |
| FIN-3 | Report totals, authorized XLSX and safe exported strings | finance_export.py; expense_repository.py | finance.view | mysql_finance_reporting_smoke; Finance browser; GUI report | PASS | SQL suffix; Finance/GUI screenshots | None | No production export memory benchmark |
| HR-1 | Department/employee validation, revision conflicts and historical references | department_repository.py; employee_repository.py | departments.view/manage; employees.view/create/edit | HR validation/revision/audit + listing smoke and native HR browser | PASS | 38-suite evidence; HR validation browser | None | Employment lifecycle integration is unsupported/unapproved |
| HR-2 | Attendance unique day, times/status, retained errors and permitted edits | attendance_repository.py; attendance_validation.py | attendance.view/manage | mysql_attendance_smoke; Attendance browser | PASS | 38-suite evidence; Attendance browser | None | No new employment-status eligibility policy |
| HR-3 | Leave calendars/balances, approval/rejection/cancellation and Attendance effects | leave_repository.py; leave_validation.py | leave.view/manage/approve | mysql_leave_smoke; Leave browser; freshness regression | PASS | SQL suffix; Leave browser | None | Later real-world corrections need owner policy |
| HR-4 | HR reports, read-only controls and concurrent edits | employee_listing.py; leave_export.py; app.py | employees.view; attendance.view; leave.view | listing/HR/Leave/Attendance suites and full GUI HR group | PASS | 38-suite evidence; browser/GUI logs | None | No human UAT or salary certification |
| PAY-1 | Inclusive nonoverlap schedule create/edit races and non-DRAFT restrictions | payroll_period_repository.py | payroll.view/process | mysql_payroll_schedule_smoke; schedule unit tests | PASS | SQL suffix; 6 focused unit tests | None | Scheduling does not certify valid salary cutoffs |
| PAY-2 | Compensation create/edit, entry generation dedup and immutable prior snapshots | payroll_repository.py; payroll_entry_repository.py | payroll.compensation.manage; payroll.process | new real authenticated HTTP rehearsal | PASS | erp_release_rehearsal_verified.log | None | MONTHLY synthetic fixture only |
| PAY-3 | Calculation and exact adjustment add/delete reversal | payroll_calculation_repository.py; payroll_adjustment_repository.py | payroll.process | real HTTP rehearsal + original audit/freshness regression | PASS | rehearsal_verified.log; original audit; SQL suffix | None | Existing arithmetic unchanged, unsupported pay types not certified |
| PAY-4 | Submit/return/approve/pay, paid payslip and historical period/entry views | payroll_workflow_repository.py; app.py | payroll.view/process/approve/pay | HTTP rehearsal; native separate-role freshness browser; audit smoke | PASS | rehearsal_verified.log; freshness browser | RV-02 negative audit identity corrected | APPROVED recovery deliberately unimplemented |
| PAY-5 | Same-second/ABA/move/reassignment/insertion/cutoff/Leave stale evidence | payroll_freshness.py; Attendance/Leave repositories | existing source-write and Payroll permissions | original audit + 15 freshness scenarios | PASS | erp_release_original_audit.log; freshness smoke log | None | Cooperating writers only |
| PAY-6 | Complete durable snapshots; both race orders; safe timeout/deadlock/uncertain commit | payroll_freshness.py; Payroll mutators | existing Payroll permissions | sixteen RR/RC races; actual 1205/1213 and lost-ack faults | PASS | SQL suffix/mysql_payroll_freshness_smoke.py.log | None | Global guard serializes all participants |
| MIG-1 | Fresh/legacy/partial/repeat 010; missing/incompatible schemas fail closed | migration 010; schemas; schema_compatibility.py; database.py | explicit synthetic operator; no runtime DDL | migration smoke + new real HTTP admission rehearsal | PASS | migration smoke log; rehearsal_verified.log | None | Implicit DDL commit and global outage require coordinated rollout |
| MIG-2 | Backup/restore exact rows, restored readiness/staleness and PAID preservation | tests/mysql_release_rehearsal.py | disposable root only | mysqldump/mysql exact 32-table restore + real transitions | PASS | erp_release_rehearsal_verified.log | None | No company backup/RPO/RTO verified |
| IT-1 | Asset category/register/custody/return/maintenance/lifecycle and reports | it_asset_repository.py | it_assets.view/manage | six IT smoke groups; security/IT Chrome compositions | PASS | 38-suite evidence; browser logs | None | No inferred assignee-only or self-service policy |
| IT-2 | Ticket create/assign/start/resolve/close, history/audit and denied writes | help_desk_repository.py | helpdesk.view/manage | mysql_helpdesk_smoke; Help Desk and composed IT browsers | PASS | 38-suite evidence; Help Desk browser | None | Request-scoped permission contract retained |
| GUI-1 | Five-width navigation/forms/tables/states/long text/validation/print styling | templates; static/css/style.css; static/js/navigation.js | manager/approver/reader/denied/anonymous as applicable | full GUI all + Procurement/catalog/Warehouse/tables + navigation | PASS | GUI/browser logs and screenshots | RV-01 corrected | Physical devices and physical print/PDF pagination not certified |
| GUI-2 | AX accessible names/landmarks/headings and actual keyboard focus ring | tests/browser_release_accessibility.cjs | manager on representative module pages | 55 page-width cases in Chrome and Edge | PASS | Chrome and isolated Edge accessibility logs | Environment retry recorded | Partial automated checks; not full contrast/WCAG/screen-reader certification |
| SEC-1 | CSRF, SQL-injection-shaped filters, Jinja/XLSX escaping and unauthorized operations | csrf_security.py; security.py; validation/export helpers | all established route guards | full Python, SQL and browser security assertions | PASS | test report and evidence JSON | No new P0/P1 confirmed | Not a complete penetration test or vulnerability database audit |
| OPS-1 | Production TLS/proxy/hosts, real DB least privilege, monitoring, company restore/UAT | security.py; .env.example; deployment checklist | target-specific owner approval | review only; no live target operations | NOT TESTED | deployment checklist | Essential production gates open | No public deployment authorized |
| PERF-1 | Bounded guard timing and resource cleanup/failure handling | repositories; release rehearsal | synthetic operator | 20 serial + 12/four-worker calculations; cleanup/fault suites | PASS | rehearsal_verified.log; 544 unit tests | Socket exhaustion under parallel suites recorded | No representative production capacity/SLA established |
| UNSUP-1 | DAILY/HOURLY salary certification, employment lifecycle and approved recovery | existing Payroll policy docs | unapproved policy | not implemented as certified workflows | NOT APPLICABLE | readiness decision register | Owner decisions open | Do not demonstrate these as supported certified features |


## Completion checkpoint - independent release verification

All required local groups completed in their final applicable attempts. Baseline
CI completed successfully. Final counts: 544 Python tests (11.719 s), 11 navigation
tests, 38 SQL smoke suites plus original audit and new rehearsal, 183 Python files,
110 Jinja templates and 30 JS/CJS files checked; pip/whitespace PASS. No skipped
business/security assertions, no runtime/schema/policy change and no company data.

The full browser batch has eleven final passes, with the failed tables run replaced
only by its successful unchanged isolated retest after the approved expectation
fix. Chrome GUI all, dedicated freshness and additional Chrome/Edge AX runs pass.
RV-01 stale expected GUI contracts and RV-02 negative audit identity were corrected
with focused regressions; original C-05 audit assertions remain byte unchanged.
No new P0/P1 implementation defect was confirmed. Production policy/operations
remain gates rather than silently implemented restrictions.

Portfolio/Demo: READY for clearly labeled isolated synthetic supported scenarios.
Internal Pilot: NOT READY. Production: NOT READY. Full scope/decisions are in the
readiness document. Physical devices, human screen readers, full contrast/WCAG,
Firefox, actual PDF/printer pagination, live TLS/proxy/host controls, company backups,
least-privilege production accounts and realistic capacity remain NOT TESTED.

Source review and deployment configuration review are complete. Auth revocation is
request-scoped, audit is best effort, copied sessions have no per-device revocation,
no rate limiter/MFA is supplied, and external/mixed-version writers are unsupported.
The deployment checklist requires separate target-specific authorization and all
backup/drain/migration/coordinated-worker/readiness/resumption steps.

Final release rehearsal expands beyond the first timing checkpoint: real HTTP
compensation create/edit, two generated entries with deduplication, exact adjustment
add/delete reversal, submit/return/resubmit/approve/pay, paid payslip/history and
exact period-number central audit sequence PASS. Final timing sample: median
40.387 ms/max 50.094 ms (20 serial), 103.797 ms total (12 operations/four workers).
These replace the earlier timing sample for the final report, without claiming capacity.

Evidence summary: docs/ERP_V1_RELEASE_EVIDENCE.json. Raw artifacts remain in %TEMP%
with log hashes recorded. Cumulative file manifest and local commits are recorded
at final delivery. Nothing is pushed, merged, tagged, deployed or run on company data.


## Local review scope and commits

- 99e09e64a41760cc7954656bb2fb8f895253f974 - four verified contract/audit test corrections.
- b33aad184893e27c6ec681145bec64f30fd0706b - three new release rehearsal/accessibility test files.
- Release documentation/evidence and README follow in separate local commits; final SHAs supplied at delivery.

Exactly 16 changed files relative to the verified merged baseline:

- `ERP_V1_CHANGELOG.md`
- `ERP_V1_DEPLOYMENT_CHECKLIST.md`
- `ERP_V1_KNOWN_ISSUES.md`
- `ERP_V1_RELEASE_READINESS.md`
- `ERP_V1_RELEASE_VERIFICATION_PROGRESS.md`
- `ERP_V1_TEST_REPORT.md`
- `README.md`
- `docs/ERP_V1_RELEASE_EVIDENCE.json`
- `docs/ERP_V1_ROUTE_PERMISSION_INVENTORY.csv`
- `tests/browser_gui_tables_forms.cjs`
- `tests/browser_release_accessibility.cjs`
- `tests/gui_contracts.py`
- `tests/mysql_payroll_freshness_browser.py`
- `tests/mysql_release_accessibility_browser.py`
- `tests/mysql_release_rehearsal.py`
- `tests/test_payroll_schedule.py`
