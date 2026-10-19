# Payroll policy management — Step 5A.2B

This checkpoint adds policy management on top of migrations 004 and 005. It
does not enable a new salary calculator, generate periods, bind historical
periods, or make the proposed development template company-approved policy.
Existing salary formulas, compensation snapshots, freshness checks and legacy
NULL policy references remain unchanged.

## Operations and safeguards

The dedicated repository lists versions, reads details and activation history,
creates DRAFT versions, edits DRAFTs, explicitly approves and seals a version,
and schedules an approved version. No deletion, cancellation or replacement
workflow is added. Approval and activation are distinct operations.

Validation matches migration 005's bounded JSON vocabulary, column limits and
fixed monthly semi-monthly development template. Unknown keys, duplicate JSON
keys, nonfinite numbers, unsupported values and malformed dates are rejected.
Effective dates must be the first or sixteenth of a supported MySQL date.
Submitted form values survive validation and stale-revision errors.

Draft writes compare the submitted revision under a row lock and increment it
exactly once. Approval revalidates the full configuration, rejects UNRESOLVED
rules, requires explicit confirmation and a meaningful approval reference, and
records the authenticated actor. A versioned canonical SHA-256 seal includes the
policy identity, configuration and approval reference. Approved content remains
protected by the existing database triggers. A reference and attestation are
recorded evidence; the application cannot independently authenticate an external
company approval document or determine legal compliance.

All writes acquire the existing Payroll coordination guard before policy and
period row locks. Version allocation, concurrent draft edits and activations are
serialized. Activation verifies the seal, requires a strictly future local date,
checks it again immediately before insertion, and appends after the latest
scheduled date. Duplicate, backdated and inserted historical activations fail.
Non-cancelled policy-linked periods whose end date reaches the proposed boundary
block activation. Cancelled records and legacy NULL references are not rewritten.
No retry is performed after an uncertain commit outcome.

The explicitly approved company-local setting is `ERP_PAYROLL_TIMEZONE=Asia/Manila`.
The application defaults to that value; invalid or empty overrides block
activation. Eligibility uses an aware UTC clock converted through ZoneInfo,
independent of the host timezone. Existing database audit timestamp conventions
are unchanged. Install the pinned tzdata dependency, particularly on Windows.

## Authorization, audit and deployment

Reading requires `payroll.view`. Creating/editing requires
`payroll.policy.manage`; approval requires `payroll.policy.approve`; activation
requires `payroll.policy.activate`. UI controls match backend checks. Existing
fresh authorization and global CSRF remain authoritative. There is no implicit
Super Admin grant or bypass, and no new separation-of-duties restriction.

The explicit, repeatable `database/payroll_policy_permissions.sql` registers
only these three permission catalog entries. It grants nothing and never runs
automatically. Before deployment, an authorized operator must verify migrations
004/005 and their triggers using the existing controlled upgrade procedures,
review the selected database, register the catalog entries, and separately review
each intended role grant. This task did none of those operations on an actual
company database. No new schema migration is required. Retain the existing
additive schema for an application rollback; do not remove policy history.

CREATE, UPDATE, APPROVE and ACTIVATE events use the central best-effort helper
after the business commit. Events contain the authenticated actor, numeric policy
ID, version and effective date, without full configuration or approval-reference
contents. Rejected, stale, duplicate, unauthorized and rolled-back operations
produce no success audit. Audit storage failure preserves the committed business
operation; this intentionally means a committed action can lack a stored event.

## Verification

- Complete Python suite: 299 passed. JavaScript suite: 11 passed.
- All 22 disposable MySQL smoke suites passed: policy schema and management;
  Payroll freshness, monetary and period invalidation; central audit and security;
  Finance payment, validation, reporting and audit; stock, inventory master and
  reporting; Procurement and receiving; IT authorization, lifecycle, validation,
  audit, reporting and category validation.
- New MySQL coverage includes five observed two-writer lock races: edit/edit,
  edit/approval, duplicate activation, conflicting same-date activation and
  version allocation. It also covers SQL rollback, all four audit-storage failure
  cases, guard timeout, midnight eligibility changes, pinned periods, exact
  revisions, hash validation, fresh revocation, disabled users and CSRF.
- Real Chrome 155.0.8059.80 passed native policy creation/correction, stale draft
  forms, approval, scheduling, viewer restrictions, forged POST rejection, CSRF,
  exact audit actors, duplicate rejection, permission revocation and disabled
  accounts, plus the existing browser security/IT checks. Browser fixtures used
  isolated MySQL and synthetic explicitly granted roles only.
- Python/Jinja compilation, JavaScript syntax, dependency and diff checks are
  included in the final checkpoint verification.

## Manual review and remaining decisions

Review styled desktop/mobile layouts, keyboard navigation and validation messages
in the deployed browser environment. Verify the four separate permission profiles
and intended approved role grants; check current, scheduled and superseded labels
around Manila midnight. Confirm staging HTTPS/Secure cookie configuration and
timezone dependency availability. No production-browser or production-load claim
is made; the shared guard deliberately serializes relevant HR/Payroll writes.

Company approval is still needed for actual attendance, leave, eligibility,
deduction and payment rules and their supporting approval references. Whether
approvers may approve their own drafts remains a company decision; this checkpoint
adds no prohibition. Schedule cancellation/replacement and correction processes
need separate approval. Step 5A.2C period generation and Step 5B salary calculation
must implement their own coordinated policy binding and interpretation. A policy
shown as active here does not yet change existing salary calculations.

## File manifest

Application: `app.py`, `payroll_policy_repository.py`,
`payroll_policy_validation.py`, `.env.example`, `requirements.txt`,
`database/payroll_policy_permissions.sql`, `templates/partials/navigation.html`,
and the four `templates/payroll/policies/` templates (index, detail, form, history).

Tests: `tests/test_payroll_policy_management.py`,
`tests/mysql_payroll_policy_management_smoke.py`,
`tests/browser_payroll_policy.cjs`, `tests/browser_security_review.cjs`,
`tests/mysql_security_review.py`, `tests/test_csrf_security.py`,
and `tests/test_horizontal_navigation.py`.

Documentation: this file and `database/migrations/README.md`.
