# ERP v1 cleanup progress

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


Assignment 2 audit and safe repairs are complete; **release acceptance is BLOCKED**
by C-05 Payroll freshness and the D-03 salary-policy acceptance gate documented in
ERP_V1_CLEANUP_REPORT.md. This is not production-readiness certification.
Earlier checkpoints below retain their historical pending states.

Current blocker-resolution continuation: investigation complete; C-05 remains
unresolved. A concrete additive schema/legacy/payment proposal is in the report.
Application/schema implementation is paused under section 5 of the user's
blocker-resolution instructions pending owner decisions. Original five local
commits remain unchanged. This continuation is not a fix or publication approval.

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

## Blocker-resolution continuation checkpoint

- Baseline verified: feat/erp-v1-final-cleanup, clean initial tree, HEAD 27bf6cf06aadd8e3943892d049ffbc42cb70d7f7, exactly the five original full cleanup SHAs and merged GUI ancestry.
- Read the reports, unchanged audit probe, calculation/workflow/entry/period/adjustment code, Attendance and effective Leave writers, relevant routes, schemas and migration/test conventions. No audit restart or unrelated refactor.
- Unchanged original probe rerun: exit 1, same-second defect reproduced. Log %TEMP%/erp_freshness_resolution_baseline.log.
- New investigation runner completed 15 actual disposable MySQL scenarios, including both validation-to-commit races held with test events. It exits 1 explicitly because no fix is present. Log %TEMP%/erp_freshness_resolution_investigation.log. Same/later-second controls, before-calculation changes, ABA edits, recalculation, moved/reassigned rows, replacement insertion, cached missing-day guard, cutoff edits, approval, payment and repeated submissions are recorded separately in the report.
- Confirmed current behavior: source writers can commit while Payroll is held after validation/before commit; submit and approval still commit. Later-second edits normally reject; moving a row out of scope evades the inner join. Payment after an approved-run source edit remains permitted and requires explicit policy assessment.
- Prepared (not implemented): additive guard, employee/date generation tombstones, per-entry daily snapshots and nullable evidence/version/scope metadata; writer coordination, current reads, scoped validation, migration/fresh-install/rollback/legacy plan and exact post-approval test matrix.
- Required decisions: approve development/disposable schema implementation; approve fail-closed legacy DRAFT/PROCESSING evidence requiring explicit recalculation; choose stale/unknown APPROVED payment handling and recovery procedure. Recommended payment rejection is a proposal, not an activated policy. No PAID rewrite, automatic replay/recalculation, migration execution or paused-branch integration.
- Changed only the two cleanup documents and tests/mysql_payroll_freshness_investigation.py. No application, schema, migration, original audit assertion or prior commit changed. Working-tree cumulative manifest is now 25 files; the committed five-cleanup-commit scope remains the prior 24.
- No new fix commit. Original 532 Python / 11 navigation / 36 smoke results remain historical; no claim that they verify this proposal. Full fix verification and original probe PASS are still required after approval.
- Severity unchanged: no identified P0; 2 P1 fixed and C-05 P1 unresolved; 3 P2 addressed. D-03 salary-policy acceptance remains separate. Assignment 2 is not ready for publication. No push, merge, deployment, company DB operation or Assignment 3.
