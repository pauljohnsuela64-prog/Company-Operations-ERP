# ERP v1 cleanup progress

Assignment 2 is in progress; this is not a production-readiness certification.

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
