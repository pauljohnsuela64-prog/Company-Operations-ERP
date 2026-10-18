# Payroll Step 2: approved freshness design and deployment requirements

Baseline: `fix/payroll-reliability`, checkpoint `928b8d1`.
The user approved the additive migration/coordinated safeguards and blocking payment
of unverifiable legacy APPROVED runs. This authorizes implementation and disposable
MySQL tests, not migration of company databases. No salary formula or role grant
is changed. All changes await review before a Git checkpoint or Step 3.

## Implemented safeguards

A DRAFT period date edit locks coordination, then period, then entries. Its date
update and invalidation commit together. Cached counters/amounts are cleared,
status becomes DRAFT, calculated_at/by and fingerprint/version become NULL.
Saved compensation snapshots and individual adjustment records remain unchanged.
Metadata/pay-date-only edits do not invalidate the current salary calculation.
Non-DRAFT periods remain uneditable. Inconsistent DRAFT parents cannot permit
recalculation, date invalidation or adjustments of APPROVED/PAID children.

New calculations atomically store version-1 SHA-256 evidence with their amounts.
Canonical evidence covers period start/end, saved entry identity/pay type/rate/
currency, weekday attendance row identities/dates/statuses, applicable APPROVED
leave intervals and paid/unpaid classification, and adjustment identities/types/
amounts. It also seals the cached calculation outputs/counters, so modified totals
cannot silently pass as the original result. Ordering and exact Decimal text are
stable; status, actor/timestamps and mutable employee display metadata are excluded.

Master compensation edits do not make the saved compensation snapshot stale.
Notes and clock times are excluded because the current monthly formula ignores
them. Hire/termination rules are not invented. A different formula/input contract
must extend the evidence and bump its version before reuse. Query-level evidence
may conservatively require recalculation after a leave change even when the final
amount would happen to be identical. It does not retain original source details
or replace source history and central business-action audit coverage.

Submission, approval and payment independently verify all entry evidence inside
their business transaction. NULL/unknown evidence or changed inputs/results reject
with a user-facing error. Second-resolution timestamps are not authoritative.
Adjustment changes retain their records and refresh the preview totals, but reset
the entry to DRAFT with NULL evidence/calculation markers, requiring recalculation.
Audit events remain after successful business commits and best-effort; failed,
stale, denied and rolled-back transitions produce no success event.

## Writer coordination and races

The InnoDB `payroll_input_guard` row 1 is the first row lock in all participating
transactions: Payroll generation, period creation/edit/cancel, calculation,
adjustments and workflow transitions; Attendance creation/editing; and Leave type
and request writes, including the active approval implementation.
After the guard, existing business lock sequences run. Payroll uses period then
entries; source evidence uses current locking reads. Coordination remains held
through commit, so an HR write cannot slip between validation and finalization.
If HR wins first, finalization sees its committed changes; if Payroll wins first,
HR waits until the transition commits. Later source changes never rewrite PAID
values. No new HR correction prohibition or separation-of-duties rule is added.

All participating lock timeout/deadlock paths roll back and produce retry/reload
errors. They do not automatically replay payment. The singleton conservatively
serializes unrelated HR/payroll writers and is not production throughput-certified.
Direct SQL and old application workers ignoring the protocol remain outside its
guarantee. Controlled schema upgrade and coordinated worker cutover are mandatory.

## Migration 004 (explicit, repeatable; never automatic)

`database/migrations/004_payroll_freshness.py` adds nullable
`calculation_input_version SMALLINT UNSIGNED` and ASCII/binary
`calculation_input_hash CHAR(64)` to payroll_entries, plus the InnoDB coordination
table/row. Fresh schema definitions include the same additions. The guard is in
core_schema so HR installations have it even before Payroll is configured.

The upgrade checks required tables use InnoDB, validates existing column/guard
shapes, supports repeat/interrupted application, and rejects incompatible existing
definitions. It does not backfill fingerprints, alter roles, rewrite amounts or
change old statuses. MySQL DDL implicitly commits; an interruption requires rerunning
the upgrade, not assuming rollback removed an already-added column.

Before any real deployment: obtain the separately required operational approval,
back up/verify restore, pause all participating writes across every worker, run the
explicit migration against the operator-selected database, verify schema/engines,
deploy all coordinated writers, then resume. No mixed-worker rolling upgrade can
claim freshness safety. Never run this against an actual database from this task.
Keep additive schema if reverting code; older code does not provide these guarantees.

## Existing payroll and unresolved policy

- DRAFT with NULL/stale evidence: explicit recalculation using its saved compensation
  snapshot is required; no implicit attestation/backfill.
- PROCESSING with NULL/stale evidence: existing return-to-Draft, recalculate/resubmit.
- APPROVED with NULL/stale evidence: payment blocked as approved by the user; all
  historical values/statuses preserved. An authorized verification/correction or
  reopening process still needs company policy. There is no override endpoint or
  automatic reset/recalculation in this change.
- PAID: unchanged and readable; no recalculation/reversal or historical repair.

The current formula still pays 50% of monthly rate and uses Monday-Friday workdays.
Freshness proves use of unchanged inputs, not that arbitrary cutoffs are valid.
Supported semi-monthly cutoffs, exceptional periods, proration/rounding and employment
rules still require company approval before salary finalization can be certified.
The existing period page explicitly flags this blocker. No new calendar restriction
or formula is imposed. DAILY/HOURLY calculation remains unimplemented.

Draft compensation snapshot refresh, missing-employee roster review, approved-run
correction/reopening, approval separation and calendar policy remain decisions.
Previously assessed monetary precision/aggregate overflow, period-overlap preflight
races, incomplete payroll audit coverage and historical employee display snapshots
remain separate work; these freshness safeguards do not claim to fix them.

## Verification scope

`tests/test_payroll_freshness.py` covers legacy/mismatched evidence, first-lock
coverage, timeout/deadlock/missing-upgrade errors and migration import safety.
`tests/test_payroll_period_invalidation.py` covers date-edit ordering/rollback.
The two corresponding disposable MySQL suites test date invalidation/recalculation,
unchanged snapshots/adjustments, legacy evidence, migration repeat/interruption and
incompatibility, same-second changes at all three workflow stages, source removals/
date moves/leave changes, late rollback, eight real Attendance/Leave coordination
waits in both winning orders, lock timeout and a deliberately opposite-order external
writer deadlock, historical child safeguards, explicit retry, CSRF and revocation.

Existing central-audit MySQL fixtures now perform real calculations before testing
workflow events; they no longer fabricate CALCULATED/APPROVED rows without evidence.
Audit unit tests retain their transaction-boundary stubs; real evidence verification
is exercised by the dedicated MySQL suites. Full regression results accompany review.

Manual acceptance: verify period date-edit warning and zeroed DRAFT values, retained
adjustment rows, explicit recalculation, stale submit/approve/pay messages, legacy
APPROVED payment denial with unchanged values, PAID payslips, and role-based controls.
No Chrome/native Payroll workflow certification or production load claim is made.

## Final regression results and file manifest

276 Python tests, 11 JavaScript tests and nineteen disposable MySQL suites passed:
Payroll freshness/date invalidation; central audit/security; four Finance suites;
Inventory stock/master/reporting; Procurement/receiving; IT Asset lifecycle,
validation, audit, reporting, category validation and IT/Help Desk authorization.
Eight finalization/HR guard waits, two date-edit races, real deadlock/timeout,
late rollback, schema compatibility and stale/legacy audit rejection were verified.
The salary arithmetic/constants and existing permission decorators were checked
against the starting commit and remain unchanged. Python/Jinja compilation,
CJS syntax, dependency and whitespace checks passed. No company database migration,
commit, push or branch change was performed. Browser acceptance remains manual.

Files modified/added:

- app.py
- attendance_repository.py
- leave_repository.py
- payroll_adjustment_repository.py
- payroll_calculation_repository.py
- payroll_entry_repository.py
- payroll_period_repository.py
- payroll_workflow_repository.py
- payroll_freshness.py
- database/core_schema.sql
- database/payroll_calculation_schema.sql
- database/migrations/004_payroll_freshness.py
- database/migrations/README.md
- templates/payroll/periods/view.html
- tests/mysql_audit_smoke.py
- tests/test_business_audit.py
- tests/mysql_payroll_freshness_smoke.py
- tests/mysql_payroll_period_invalidation_smoke.py
- tests/test_payroll_freshness.py
- tests/test_payroll_period_invalidation.py
- PAYROLL_FRESHNESS_PROPOSAL.md
