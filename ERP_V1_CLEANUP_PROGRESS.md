# ERP v1 cleanup progress

Assignment 2 audit and safe repairs are complete; **release acceptance is BLOCKED**
by C-05 Payroll freshness and the D-03 salary-policy acceptance gate documented in
ERP_V1_CLEANUP_REPORT.md. This is not production-readiness certification.
Earlier checkpoints below retain their historical pending states.

## Verified prerequisites

- PR #29 merged at 2026-10-23 03:53:19 UTC as `ee7e49b061a43891d9593f251fcf868004e85e2d`.
- Fetched `origin/main`; GUI head `1f8d47c4dcd4a5549dfd748a5c7aa33bf44eea5c` is its ancestor.
- GitHub Actions run 39892236332: Python unit tests and syntax, JavaScript tests and syntax, and Disposable MySQL integration all completed successfully.
- Clean starting tree; existing GUI reports/templates present. Created `feat/erp-v1-final-cleanup` from that mainline without altering existing branches.
- No publication, production/company database access, grants, migrations or paused-branch merges authorized.

## Audit checkpoint

| Area | Review/evidence | Status |
| --- | --- | --- |
| Authentication/shared infrastructure | Read security.py, csrf_security.py, database.py and CI workflow; refreshed authorization, signed credential markers, session expiry, CSRF recovery and schema lease identified | Further route/tests review pending |
| Suppliers | Read validation, repository, documentation and unit tests; optional email has native browser/backend syntax mismatch | Reproduction and safe contract correction under investigation |
| Procurement | PR separation-of-duties decision must remain pending owner approval | Pending |
| Inventory | Historical UOM/master labels and warehouse references require explicit policy assessment | Pending |
| Finance | Transaction, decimal and payment audit | Pending |
| HR/Payroll | Mainline-only lifecycle/policy audit | Pending |
| IT/Help Desk | Transition, assignment, maintenance and report audit | Pending |
| Administration | Last-admin, exports, denied mutations and audit integrity | Pending |

## Remaining work

Inventory actual routes/repositories/schema/tests/deployment and prior reports; reproduce concrete defects, make only safe focused repairs with regression tests, run final verification, create logical local commits and final report. No Assignment 2 test result is yet claimed. Previous GUI test evidence is prerequisite evidence only.

## Confirmed repairs

### C-01 - P1: receiving could automatically replay uncertain transactions

Reproduced with actual transaction function and mocked connections: a lock-number error raised by COMMIT or failed ROLLBACK opened three connections instead of one. The retry loop trusted errno 1205/1213 without transaction-phase evidence. No duplicate persisted delivery is claimed; UUID protection remains, but automatic replay violated the established uncertain-commit contract.

Small correction follows the existing Stock approach: only an internal pre-commit/confirmed-rollback marker authorizes bounded retries with the same normalized payload/UUID. Commit and cleanup errors do not qualify. Cursor creation/close failures now still close the held connection. No SQL, business transitions, grants or schema changes.

Verification: `python -B -m unittest discover -s tests -p test_receiving_safety.py -q`: initially two new regression failures (three calls), then 10 passed. `python -u -B tests/mysql_receiving_smoke.py`: passed on verified disposable MySQL; expanded real-commit acknowledgment faults 2013/1205/1213 each perform exactly one commit, then explicit same-UUID reconciliation preserves exactly one delivery. Existing races, six write-stage rollbacks, CSRF recovery, receiving/cancellation, audit and reference checks pass. Log: `%TEMP%/erp_cleanup_receiving.log`.

C-02 supplier native/email reproduction failed as expected (`email` vs established text contract). Minimal form correction and focused test currently pass (15 supplier tests); Chrome and integration verification pending. Keep this fix in a separate local commit.

### C-02 - P2: Supplier native forms rejected historically accepted email text

Corrected only the two input types to text; code/name requiredness, optional contact fields, max lengths, values, escaping, CSRF, backend validation and schema remain unchanged. Focused supplier suite: 15 passed. Native Chrome Add/Edit now create and retain `Legacy <billing> contact` through requestSubmit, alongside blank optional-field submission and escaped redisplay. Existing Supplier, authentication/CSRF and all 17 IT/Help Desk authorization workflows passed in the composed runner. Manager, viewer, IT Manager and Super Admin exercised; no denied-request mutations or historical-fixture changes.

Command: `python -u -B tests/mysql_supplier_management_browser.py`. Initial sandbox attempt crashed Chrome before assertions (ECONNRESET and locked Crashpad cleanup); rerunning outside the sandbox passed with Chrome 155.0.8059.85. Log `%TEMP%/erp_cleanup_supplier_browser_retry.log`. The initial attempt is not a pass. Disposable MySQL suite batch is now running; receiving is excluded because its expanded suite already passed.

Local receiving repair commit: `5c523a1` (full SHA recorded in final report).

## Expanded audit checkpoint

- C-03 P1 confirmed/fixed locally: two actual concurrent Payroll creates passed both preflights and committed overlapping periods (before-fix outcomes IDs 2 and 1). Creates/edits now serialize using the existing payroll.process permission row as a lock only; no grants/schema added. Current overlap read shares the transaction with the write. Cancellation eligibility, inclusive dates, DRAFT-only edits and monetary behavior remain. Focused tests: 5 passed. Disposable create/create, create/edit and edit/edit races pass under RR/RC; boundary/cancelled/paid/missing-gate checks pass. Chrome late create/edit conflict recovery, retained escaped values, corrected native saves and viewer denial pass. Additional lock-wait check pending.
- C-04 P2 confirmed/fixed locally: login lookup and per-request authorization leaked held connections if cursor allocation or cursor close failed. Fault injection reproduced zero connection.close calls. Two small nested-finally corrections preserve SQL and fail-closed propagation. Three regression tests and 19 session-security tests pass; cross-module MySQL batch pending.
- C-05 P1 UNRESOLVED RELEASE BLOCKER: actual calculation followed by actual same-second PRESENT->ABSENT attendance edit is accepted by mainline payroll submission. `python -u -B tests/mysql_payroll_freshness_audit.py` exits 1 with explicit assertion; log `%TEMP%/erp_cleanup_payroll_freshness.log`. Do not count this as a passing suite. Timestamp greater-than comparison cannot establish source freshness. Stopped this workstream: durable evidence/coordinated Attendance/Leave/Payroll writes and legacy APPROVED-run handling require a separately reviewed integration/schema plan. Read paused Payroll freshness/design docs with git show only; no branch merged and no migration executed. Assignment 2 cannot be reported unconditionally complete.
- Existing documentation findings: old Security reports still list fixed IT view-write authorization and Procurement navigation issues as current; tests README has outdated CI timeout/first-run wording. Documentation correction pending.
- Remaining resource-cleanup debt: legacy cursor-before-try patterns remain in older repositories. Automated scan reports candidates, not independently confirmed defects; only authentication hot paths and changed receiving/schedule writers are repaired in this pass.

## Module coverage reviewed so far

Read actual route/decorator inventory, all 26 repository function inventories, dynamic SQL construction sites, schema admission/migration manifest, authentication/CSRF, shared exports and templates/navigation. All 232 constant template url_for references resolve to known endpoints; no template safe filters or application innerHTML/eval/document.write sites found. No tracked .env. Detailed review includes Procurement parent/item/status/receiving transactions, Stock UUID/current-read/balance locks, item UOM edits/current-label joins, Finance expense-budget lock order/Decimal/reference locks, HR revisions and Attendance/Leave source semantics, Payroll generation/calculation/workflow/period/adjustments, IT custody/maintenance and Help Desk transactional history, and Admin guardian/last-active-Super-Admin protections. Existing suites provide module evidence; no blanket claim that every path is verified.

Supplier final Chrome rerun including persisted legacy email assertion passed (`%TEMP%/erp_cleanup_supplier_browser_final.log`). Local supplier repair commit `8b529d4`. Applicable MySQL batch runs sequentially and logs individual successes in `%TEMP%/erp_cleanup_mysql.log`; do not claim later suites until completed.

## Verification checkpoint after application fixes

- Complete Python suite: 532 passed (12.781 seconds), `python -B -m unittest discover -s tests -q`, log `%TEMP%/erp_cleanup_unittest.log`.
- JavaScript navigation: 11 passed, `node --test tests/horizontal_navigation.test.cjs`.
- Dependencies: `python -m pip check` passed.
- Final schedule MySQL suite passes, including observed wait on the actual permissions row via performance_schema.data_lock_waits. An earlier diagnostic used innodb_trx.trx_query filtering and failed to observe the wait; replaced with the precise waiting-table join, retaining the required actual-wait assertion.
- `mysql_security_smoke.py` passed after the authentication cleanup, covering committed revocation/role changes, disabled users, credential invalidation and real login. Authentication fault tests (3) and session-security tests (19) also pass.
- Schedule fix local commit: `d2893958facc0dd5e3849a09265943ce743fc876`. Remaining MySQL batch/syntax/final audit documentation pending. The explicit freshness audit remains FAIL/P1 and is not included in the 532 passing unit-test count.

## Final audit checkpoint

- All major modules reviewed; current findings, evidence, severity, unresolved policy and Assignment 3 recommendations recorded in ERP_V1_CLEANUP_REPORT.md.
- C-01/C-03 P1 and C-02/C-04 P2 repairs verified and committed separately. C-06 P2 documentation correction included in final checkpoint. C-05 P1 remains deliberately reproducible, not suppressed. Six findings: 3 P1/3 P2; 5 addressed, 1 implementation release blocker remains.
- Full 532 Python / 11 navigation tests and dependency checks passed. All 34 remaining existing MySQL suites passed (batch exit 0); together with expanded receiving and new schedule checks, 36/36 smoke suites passed. The separate freshness audit FAILED (exit 1).
- Supplier and Payroll affected Chrome workflows passed, including composed authentication/CSRF and IT authorization workflows. Final Payroll lock-wait assertion passed using actual waiting-table join, without weakening the race/rollback assertions.
- Authentication local commit: `9ddf30fab297f2b7127f418a80819d5fa42d828e`. Exact four repair SHAs and cumulative 24-file manifest are in the report. Final audit/documentation commit SHA supplied at delivery.
- No production/schema/permission changes or paused-branch merges. No push/merge. Remaining work is human review, explicit freshness/policy integration approval, then independent Assignment 3; this checkpoint does not authorize those actions.
- Final syntax: 174 Python files compiled, 110 Jinja templates parsed, 28 JavaScript files passed node --check. Cumulative git diff --check origin/main passed. Actual cumulative diff: 24 files. Final report manifest and four repair SHAs checked against Git. No expensive suites rerun after documentation-only updates.
