# Payroll Step 3: monetary and transaction integrity

Review checkpoint: `fix/payroll-reliability`, starting from clean commit
`5881af7`. Changes are uncommitted. No company database was accessed and no
actual database migration was applied.

## Corrections

- Compensation CREATE/UPDATE and adjustment CREATE validate exact Decimal
  amounts in both routes and repositories. Reject nonfinite/malformed values,
  floats, nonpositive inputs, more than two effective fractional places, and
  amounts over `9999999999.99`. Existing positive decimal exponent notation
  remains supported; grouping commas and underscores are invalid. Validation
  does not round submitted values, including trailing fractional zeroes beyond
  scale. Routes display the specific error using their existing redirect flow.
- All persisted Payroll money columns are `DECIMAL(12,2)`, including calculation
  extensions in `payroll_calculation_schema.sql`. Basic rate and individual
  adjustments must be positive; calculated values may be zero. Wider Python
  report totals are not capped as though they were individual database cells.
- Adjustment insertion checks projected earnings, deductions, gross and net
  before INSERT; recalculation checks SUM results and every monetary output
  before UPDATE. Deletion refreshes and validates totals in the same transaction.
  Any failure rolls back the whole operation, including earlier employees in a
  calculation batch. Strict and non-strict MySQL cannot silently clip these writes.
- Generation validates the saved rate before snapshot persistence. Existing
  HALF_UP calculations, half-month factor, weekday handling and zero-net floor
  are preserved. Calculation arithmetic assignments match the starting commit.
- Evidence validation checks saved monetary values and adjustment aggregates
  against database capacity. A legacy version-1 fingerprint that matches clipped
  outputs cannot permit submission, approval or payment. Valid existing hashes
  retain the same payload and version; paid records are never rewritten.
- Period CREATE and DRAFT EDIT perform an authoritative locking overlap read in
  the write transaction after acquiring the shared guard. All non-CANCELLED
  periods count, endpoints overlap inclusively, EDIT excludes itself. Existing
  route preflight checks remain advisory. Cancellation uses the same guard.
- Adjustment writes now explicitly lock parent period before child entry, then
  adjustment rows. An initial unlocked entry lookup identifies the parent; the
  locked child query rechecks that relationship. Period, generation, calculation
  and workflow writers retain guard-first coordination. No automatic retry was
  added for timeouts, deadlocks or uncertain commits.
- Permissions, global CSRF, fresh authorization, postcommit workflow audits and
  best-effort audit failure isolation remain unchanged. No new audit actions or
  permission grants were introduced.

## Files

Application: `app.py`, `payroll_validation.py`, `payroll_repository.py`,
`payroll_entry_repository.py`, `payroll_adjustment_repository.py`,
`payroll_calculation_repository.py`, `payroll_period_repository.py`,
`payroll_freshness.py`.

Tests: `tests/test_payroll_validation.py`,
`tests/test_payroll_period_invalidation.py`,
`tests/mysql_payroll_monetary_smoke.py`, `tests/mysql_security_review.py`,
`tests/browser_security_review.cjs`, `tests/browser_payroll_monetary.cjs`.
Documentation: this file.

## Verification

- Complete unittest discovery: **286 passed**. JavaScript navigation: **11 passed**.
- All **20 disposable MySQL smoke suites** passed: payroll monetary, payroll
  freshness, payroll period invalidation, audit, security, finance payment,
  finance validation, finance reporting, finance audit, stock, inventory master,
  inventory reporting, procurement, receiving, IT authorization, IT lifecycle,
  IT validation, IT audit, IT reporting and IT category validation.
- Monetary integration explicitly configures actual repository connections with
  `STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION` and empty (non-strict) SQL mode.
  Tests cover minimum/maximum inputs, HALF_UP boundary calculation, invalid
  submissions, aggregate earnings/deduction overflow, combined deduction overflow,
  unchanged prior evidence, whole-batch rollback, real SQL failure rollback and
  legacy matching fingerprints with clipped totals at all finalization stages.
- Seven new real two-writer InnoDB tests observe both transactions waiting on
  locks before release: overlapping CREATE, overlapping EDIT, CREATE/EDIT,
  nonoverlapping CREATE, cancellation/CREATE, competing adjustments and
  calculation/adjustment. Only one conflicting period or excessive adjustment
  commits. Cancellation/CREATE permits either valid serial outcome. Additional
  tests cover inclusive endpoints, finalized overlap, actual timeout and rollback.
- Existing freshness suite rechecks same-second changes, deleted/moved attendance,
  leave changes, intentional snapshots, eight HR/finalization lock waits, legacy
  approved blocking, immutable paid history, real deadlock rollback, CSRF and
  revoked permissions. Existing audit suite verifies workflow deduplication and
  audit storage failure isolation.
- Python compilation: **99 files**; Jinja compilation using application filters:
  **104 templates**. Dependency consistency (`pip check`), JavaScript syntax and
  `git diff --check` passed.
- Real Chrome **155.0.8059.80** passed compensation invalid precision/correction,
  saved entry snapshot, calculation/evidence, invalid and overflowing adjustment
  POSTs, CSRF, valid adjustment and evidence invalidation. Existing security and
  IT/Help Desk browser checks also passed. The command sandbox reset DevTools;
  the same harness succeeded outside it with unchanged browser/application
  security settings and a fresh temporary database/profile.

## Compatibility, policy and deployment limits

No new schema migration is needed. Existing migration **004** remains mandatory;
its repeatable upgrade and old/interrupted-schema checks ran on disposable
databases only. It must still use the separately documented controlled upgrade
process, with all participating writers upgraded together. Direct SQL and older
workers bypass the application coordination contract. Global guard contention
has not been certified at production scale.

No historical repair or calculation evidence backfill occurs. Old invalid totals
are rejected; a legacy oversized adjustment set may require a controlled
correction if even one deletion leaves totals oversized. Approved historical
correction remains a separate company decision. Currency conversion, salary
formulas, daily/hourly compensation, cutoffs/proration, employment eligibility,
excess deductions/negative net, snapshot refresh, statutory deductions and
approval separation remain unresolved or unchanged. Do not treat this technical
checkpoint as approval to finalize salaries under an unapproved calendar.

Manual checks still required: styled desktop/mobile Payroll forms, native
adjustment Add/Delete interactions and confirmations, period Add/Edit overlap
messages across tabs, full browser submit/return/approve/pay and payslip/report
review with company-approved synthetic scenarios. Those workflow transitions
and concurrency boundaries were tested through real repositories/HTTP/MySQL,
but not all through native browser forms. Production HTTPS/Secure cookies and
representative load remain outside this verification.

Recommendation: ready for Step 3 code review and a Git checkpoint after approval;
not production payroll policy approval. No commit/push/branch change performed.
