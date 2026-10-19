# Payroll Step 5A.2C — semi-monthly cutoff generation

This checkpoint generates policy-pinned DRAFT periods only. It does not calculate
entries, implement a new salary formula, approve payroll or mark it paid. No
company records, policies, permissions or actual databases were changed during
development. The starting checkpoint was clean `fix/payroll-reliability` at
`36562cd` (versioned policy management).

## Calendar, dates and policy resolution

`payroll_generation_repository.month_cutoffs` accepts MySQL-compatible years
1000–9999 and months 1–12. It derives inclusive Cutoff A (1–15) and Cutoff B
(16–calendar month end), including leap February and December/January. It never
adds a month beyond year 9999. The service accepts no caller-supplied boundaries
or policy IDs. The supported approved policy vocabulary fixes the calendar to
`SEMI_MONTHLY_1_15_16_EOM_V1`; unsupported configuration fails validation.

Each cutoff resolves the latest activation effective at its start, requires
APPROVED status, resolved bounded rules and a valid configuration seal, and
rejects any activation boundary inside the cutoff. Activation on the sixteenth
can select different versions for A and B. A DRAFT or approved-but-unactivated
version cannot be selected. An activation scheduled for a future month can be
used to generate that future month's periods; the selected policy must cover
those period dates, not merely be today's policy. Asia/Manila is the explicit
company timezone; invalid configuration fails closed.

Generation requires two explicit payment dates in YYYY-MM-DD format, independently
validated against each cutoff's end and the MySQL date range. There are no default
offsets, holiday/weekend adjustments or payment schedules. Preview does not
require payment dates, does not write records and is never trusted as evidence
at submission. Every generation submission resolves and validates again.

## Transactions, replay and pinning

The same transaction acquires the existing Payroll InnoDB guard first, reads and
locks the activation/policy schedule, checks overlapping non-cancelled periods,
then inserts both cutoffs. Both are validated before either insert. Every failure
rolls back all writes. The guard coordinates manual period writers, policy
activation and existing Payroll/Attendance/Leave participants; there is no
automatic retry following an uncertain commit outcome.

An existing non-cancelled period is an exact match only when its start, end,
payment date, policy ID and cutoff code all match. Exact matches are returned
explicitly without writes or additional success audits. Any overlapping conflict
rejects the whole request. If one matching cutoff already exists and the other
is absent, only the missing cutoff is created in the transaction. Cancelled
records are preserved and ignored for overlap, retaining cancel-and-recreate
semantics. Generated names include a unique suffix so cancellation does not
collide with the existing unique period-name constraint. Period numbers follow
the existing PP-ID convention.

Created records retain `policy_version_id` and `cutoff_code`. Existing editing
cannot change those references; generated start/end dates are read-only in the
form and independently protected inside the guarded write transaction. Metadata
and payment-date editing retain existing DRAFT rules. A boundary correction uses
the existing cancellation workflow, never historical reassignment. Migration 005
continues to protect referenced activations. These application protections do
not prevent unrestricted DBA changes.

## Manual compatibility and future calculator requirements

Manual CREATE remains available under `payroll.process`, with existing arbitrary
date ranges, payment-date validation and global overlap prevention. Legacy/manual
NULL references are displayed explicitly and never automatically assigned a
policy. Existing legacy date-edit invalidation remains intact. Generated records
and policy/cutoff identity appear in period list/detail views.

Before Step 5B can finalize policy-based calculations it must reject unpinned or
unsupported periods, verify exact cutoff boundaries and full policy coverage,
and validate the pinned version rather than silently re-resolving history.
An approved correction/migration procedure is needed for legacy data. This
checkpoint deliberately leaves the existing salary calculator and its unresolved
company-specific rules unchanged; generated periods do not certify compensation
accuracy or authorize production payroll use.

## Security and auditing

GET and POST generation require existing `payroll.process`. List/detail views
remain available with `payroll.view`; viewers see no generation control. Existing
fresh authorization, disabled-account checks and global CSRF apply. Unsupported
and repeated form fields are rejected. No permission identifiers or grants change.

Each newly committed cutoff emits one central PAYROLL / CREATE / PAYROLL_PERIOD
event with authenticated actor, numeric period ID, month/cutoff and policy version.
Previews, exact replays, conflicts, rollback, denial and invalid requests emit no
success audit. Logging occurs after commit and retains best-effort isolation: an
audit storage outage cannot undo generated periods. The acknowledged limitation
is that a committed operation can lack an audit row during such an outage.

## Verification results

- Complete Python suite: **306 passed**. Complete JavaScript suite: **11 passed**.
- All **23 disposable MySQL smoke suites** passed, including the new generation
  suite and existing Payroll schema/policy/freshness/monetary/invalidation,
  Finance, Procurement, receiving, Inventory, IT/Help Desk and security/audit suites.
- New integration coverage includes actual calendar boundaries; separate A/B
  versions; draft/unactivated rejection; date validation; duplicate/conflicting
  periods; legacy NULL overlap; cancellation/recreation; pinned-date rejection;
  a late B-insert failure rolling back A; and actual audit-insert failure isolation.
- Three actual concurrent pairs cover duplicate generation, activation/generation,
  and manual creation/generation. Both writers were observed waiting in InnoDB
  before releasing the guard. Tests also force a real lock timeout and an InnoDB
  deadlock using a deliberately reversed synthetic writer; business/history/audit
  records remain unchanged on rejected transactions. No application writer adopts
  the reversed order.
- Security tests cover repeated/forged fields, viewer denial/controls, CSRF,
  same-session permission revocation, disabled accounts and correct audit actors.
- Real Chrome **155.0.8059.80** passed native preview, leap February, invalid-date
  retention/correction, generation, replay/conflict rejection, audit actors,
  viewer controls and CSRF. Existing policy, Payroll monetary, cross-module
  security, IT lifecycle and Help Desk browser checks also passed.
- **110 Python files / 109 Jinja templates** compiled; JavaScript syntax,
  dependency and diff checks passed. All MySQL tests used newly initialized
  isolated servers and synthetic records. The central audit fixture was updated
  to explicitly install migrations 004/005, matching current schema requirements.

## Compatibility and manual checks

No additional schema migration is necessary. Migrations 004 and 005, their guard,
constraints, activation foreign key and protection triggers are prerequisites;
deploy only through their existing approved upgrade procedures. This task did
not apply them to actual databases. The pinned tzdata dependency and explicit
Asia/Manila configuration from Step 5A.2B remain required.

Before production review, check fully styled desktop/mobile layouts, keyboard
flow and date-picker behavior; open generated details and verify pinned labels
and read-only edit boundaries; verify intended process/view role grants in
staging; and confirm deployment HTTPS/Secure cookies and timezone availability.
Production load, TLS and company-policy approvals are not certified by local
browser tests. Existing unresolved compensation, leave, deduction, reconciliation
and legacy correction policies require company approval before salary changes.

## Files changed

- Application: `app.py`, `payroll_generation_repository.py`,
  `payroll_period_repository.py`.
- Templates: `templates/payroll/periods/generate.html`, `index.html`, `view.html`,
  `edit.html`. Existing horizontal navigation is retained.
- Tests: `tests/test_payroll_generation.py`,
  `tests/mysql_payroll_generation_smoke.py`,
  `tests/browser_payroll_generation.cjs`, `tests/browser_security_review.cjs`,
  `tests/mysql_security_review.py`, `tests/mysql_audit_smoke.py`,
  `tests/test_csrf_security.py`, `tests/test_payroll_period_invalidation.py`.
- Documentation: this file.

Ready for review toward a Step 5A.2C checkpoint after final verification. No
commit, push, merge, reset or branch switch is part of this task. Wait for review
before Step 5B.
