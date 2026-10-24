# ERP v1 final test report

Baseline: 4b927555c5e76aa236bf9924895daec4c27198df, merged PR #30.
Assignment 3 checks were executed independently from that tree on
feat/erp-v1-release-verification. Runtime source/schema/business policies were not
modified. Only stale GUI test expectations, new verification tests and documents
change in this assignment. Final retest summary is appended below.

## Environment and isolation

- Windows NT 10.0.26200, Intel Core i7-13700HX (16 physical/24 logical cores),
  16,886,128,640 bytes physical RAM. Shared local host, not a dedicated load runner.
- Python 3.14.3, Node v24.17.0, MySQL Community Server 8.0.46, pinned requirements.
- Chrome 155.0.8059.85; installed Edge 155.0.4283.62. Firefox was not installed.
- Servers: --no-defaults, dynamic 127.0.0.1 ports, selected datadir/PID checked
  against the held child. No .env company target or production data is used.
- Browser profiles/HTTP servers and test data are temporary. External resources
  are blocked; visual/AX suites fulfill only trusted local Bootstrap 5.3.8 CSS.
- Local artifact root is %TEMP%; raw logs/screenshots are not company-data exports.
  Summary evidence is committed; temporary artifacts need separate retention.

## Independent automated checks

| Command / group | Actual result at checkpoint | Evidence |
| --- | --- | --- |
| .venv/Scripts/python.exe -B -m unittest discover -s tests -q | PASS 543 baseline tests, 7.032 s | %TEMP%/erp_release_python.log |
| node --test tests/horizontal_navigation.test.cjs | PASS 11, zero skipped | %TEMP%/erp_release_navigation.log |
| scripts/ci_checks.py python | PASS 181 baseline Python files / 110 Jinja templates | %TEMP%/erp_release_syntax.log |
| scripts/ci_checks.py javascript | PASS 29 baseline files | same syntax log |
| python -m pip check | PASS no broken requirements | executed command output |
| scripts/ci_checks.py mysql then resumed exact failed-and-later suffix | PASS all 38 discovered suites; no skipped assertions | %TEMP%/erp_release_mysql.log and erp_release_mysql_resume/results.json |
| tests/mysql_payroll_freshness_audit.py | PASS original assertions unchanged | %TEMP%/erp_release_original_audit.log |
| mysql_payroll_freshness_smoke.py | PASS 15 scenarios, sixteen ordered RR/RC races, faults, Leave/legacy/evidence checks | resume/mysql_payroll_freshness_smoke.py.log |
| mysql_payroll_freshness_migration_smoke.py | PASS old/partial/repeated, optional modules and incompatible structures | resume/mysql_payroll_freshness_migration_smoke.py.log |
| tests/mysql_release_rehearsal.py | PASS real admission, 010 interruption/repeat, exact backup/restore, persisted transitions and PAID preservation | %TEMP%/erp_release_rehearsal.log |
| test_payroll_schedule.py focused rerun | PASS 6 after new narrow contract regression | %TEMP%/erp_release_contract_regression.log |

The first MySQL batch completed seven suites then stopped before expense-category
assertions when Windows denied its selected port. The suffix (31 suites, including
that failed launch) passed outside the sandbox. Do not count the initial failure as
a pass or substitute an already-running server. Exact inventory: all
tests/mysql_*_smoke.py files, reconciled with individual group/results records.

## Business workflow scope

Existing suites exercise integrated transactions, HTTP permissions and persisted
results, not merely repository mocks: receiving changes exact stock; Finance
concurrent payments enforce annual budgets; HR revisions/Leave affect Attendance;
Payroll calculation/approval/payment now depends on Attendance evidence; IT domain
history and central audit are checked after transitions. Security browser composition
also proves forged writes do not mutate business/history/audit snapshots.

See the progress matrix and docs/ERP_V1_ROUTE_PERMISSION_INVENTORY.csv for expected
behavior, sources and actual route permission names. The CSV inventories 138 static
app.route declarations and 38 decorator permission codes. It does not pretend to
enumerate test-only dynamically added control routes or certify every code path.

Large synthetic correctness fixtures include 1,005 master records and bounded
25/50/100 pagination, 501 reachable audit rows, 1,005 dashboard items, tied names,
literal wildcard/injection-shaped search, Unicode and long text. These are
correctness checks, not timed production-volume qualification. Reports/XLSX check
authorization, safe text typing and expected totals; printer output is not certified.

## Browser and accessibility checkpoint

| Suite | Actual coverage | State |
| --- | --- | --- |
| mysql_gui_v1_browser.py all | All remaining-module visual routes, five widths, manager/reader/approver where applicable; anonymous login/CSRF, labels, unique IDs, filters/forms/validation, contained tables, print CSS, runtime errors | PASS after approved-contract correction |
| GUI Procurement, catalog and Warehouse suites | Five-width long/populated/empty/unavailable states, requester/approver/manager/reader controls, native actions and persisted inventory/audit proofs | PASS |
| mysql_payroll_freshness_browser.py | Separate process/approve/pay/reader roles, native confirmations and Attendance edits, stale submit/approve/pay denial, legacy block, explicit correction and fresh payment | PASS |
| mysql_release_accessibility_browser.py --browser chrome | 55 page-width cases over 11 representative module lists, 407 named AX controls, main/heading semantics, real Tab focus rings and contained layouts | PASS |
| tables/forms composition | Supplier/category native workflows and five-width/table/validation contracts | PASS isolated rerun after approved expectation correction |
| Edge accessibility/security composition | Same additional automated AX checks and existing security/IT browser composition | PASS isolated rerun; initial socket-exhaustion attempt remains a failure |
| Finance, admin, HR validation, Attendance, Leave, Help Desk, navigation/dashboard | Native workflows, permission denials, persisted histories, filters and validation | Individual final results recorded in completion evidence |

Viewport widths: 1440, 1024, 768, 390 and 320 CSS pixels, desktop headless emulation,
height 1000, deviceScaleFactor 1. This is not physical mobile testing. Full GUI roles
vary by module; no claim that every role visits every route. Freshness separately
tests process versus approver/pay permissions and reader forged writes.

Representative screenshots inspected visually: Stock In and Payroll detail at 320,
Finance report at 1440 and emulated paid-payslip print styling. Many captures are
capped at 2400 px; DOM layout assertions cover beyond that capture region. Keyboard
table scrolling, labels and nav tests are automated; full contrast/WCAG, human
screen readers, physical printers, physical devices and Firefox remain NOT TESTED.

## Migration, backup and reliability observations

New rehearsal retains the real global schema inspector and HTTP admission, replacing
only connection selection with asserted disposable host/port/database. Fresh access
passes; removing 010 blocks readiness and login with 503/no-store and does not create
the guard. Partial/repeated migration preserves legacy business columns and unknown
evidence. mysql CLI tools dump/restore 32 tables and compare exact rows before reuse.

Restored stale evidence rejects. Explicit calculation/submission/approval/payment
succeeds; previous PAID entry unchanged. Dump SHA256:
6e0b5efb867429a18f208bdacfa84d7cb8ac507f491be47c1e2bed6f78a5cf51.
No production migration/backup, production RPO/RTO or approved-run recovery was tested.

Bounded Payroll timing: one employee, five weekdays, two periods; 20 serial explicit
calculations median 40.387 ms/max 50.094 ms. Twelve calculations at four workers took
103.797 ms total. Other release checks ran concurrently. No SLA, percentile capacity,
maximum users or production throughput can be inferred. Global guard serialization
and new connections remain deliberate integrity/architecture constraints.

Multiple concurrent high-volume browser groups exhausted Windows sockets (10048).
Some failed pages surfaced safe unavailable/error states. Reduced-concurrency
retests distinguish those environment failures from actual browser/workflow defects.
No registry/TCP tuning, connection pooling or integrity-lock weakening was performed.

## Security and deployment scope

PASS within executed contracts: valid/invalid login, logout, idle/absolute expiry,
credential invalidation, disabled accounts, current permissions, last-admin guard,
CSRF/malformed/expired/forged requests, schema outage/recovery, Jinja escaping,
injection-shaped filter inputs, XLSX text safety and audit failure isolation.

NOT TESTED: public TLS/proxy/host restrictions, real least-privilege DB account,
login abuse controls/rate limiting (not implemented), MFA (not implemented), full
dependency vulnerability scanning, human penetration test and production operations.
Request-level revocation, best-effort audit and copied-cookie limits are explicit.

## Hosted CI versus local-only verification

Baseline run 39917785782 completed all jobs successfully: Python job 120295412923,
JavaScript job 120295413186 and MySQL job 120295413697. Python includes full unittest,
dependency checks and Python/Jinja syntax. JavaScript includes syntax/navigation.
MySQL discovers 38 *_smoke.py suites, including freshness/migration/concurrency tests,
with a five-minute per-suite timeout and 60-minute job bound.

Original explicit freshness audit, Chrome/Edge, GUI/AX checks, screenshot inspection,
new release backup/restore and bounded timing are local-only. New Assignment 3 code
has not been published or run on hosted CI. Green baseline CI does not prove these
local checks or operational readiness. No assertion is removed/skipped to pass.


## Final completion evidence

- Final Python rerun after the new test correction: **544 PASS**, 11.719 seconds,
  %TEMP%/erp_release_python_final.log. The baseline run was 543; one narrow expected
  contract regression was added. New rehearsal/browser launchers are local-only,
  not extra unittest cases or auto-discovered smoke suites.
- All **38/38** SQL smoke suites reconciled with actual file discovery: initial
  seven completed groups plus the 31-suite successful suffix. The original probe
  and additional release rehearsal passed separately. No failing suite was skipped.
- All eleven browser batch suites passed in their final applicable attempts. The
  tables/forms batch attempt failed; corrected expectation then a concurrent run
  failed its Supplier page count; unchanged isolated rerun passed. This co-occurred
  with socket exhaustion, but the Supplier failure's cause is not independently proved.
- Full GUI all completed successfully; Procurement, catalog and Warehouse native
  layout workflows passed. GUI screenshots: %TEMP%/erp_release_gui_v1 and
  erp_release_browsers/screenshots. Only four representative screenshots were
  manually inspected by the agent; remaining coverage uses DOM assertions.
- Additional AX/keyboard checks PASS in Chrome 155.0.8059.85 and Edge 155.0.4283.62:
  55 page-width cases and 407 exposed named control instances per browser. They
  also run the existing native security/IT workflows. Edge initial attempt failed
  with 10048; isolated final run passed. Firefox is NOT TESTED (not installed).
- Corrected freshness audit identity Chrome rerun PASS:
  %TEMP%/erp_release_freshness_browser_verified.log. It checks period-number audit
  identity with zero paid events for stale/legacy and exactly one for valid payment.
- Extended release rehearsal PASS: %TEMP%/erp_release_rehearsal_verified.log. In
  addition to migration/restore, real authenticated HTTP exercises compensation
  create/edit, generated-entry deduplication, calculation, exact Decimal adjustment
  add/delete reversal, submit/return/resubmit/approve/pay, payslip, historical views
  and exact central audit transition order using the established period number.
- Early new-rehearsal fixture mistakes (duplicate fixture name and numeric audit
  lookup) were corrected before final success. No production rule was changed.

The final evidence JSON records individual suite names and log hashes. Raw logs
are temporary artifacts, not shipped hosted results. Final staged syntax/whitespace
counts and local commit references are recorded in the progress completion entry.

Final syntax: **183 Python files, 110 Jinja templates and 30 JS/CJS files PASS**;
staged and cumulative whitespace PASS. No expensive successful suites were rerun
for the documentation/README completion. Exactly 16 files differ from the baseline;
application and database schema files are unchanged.
