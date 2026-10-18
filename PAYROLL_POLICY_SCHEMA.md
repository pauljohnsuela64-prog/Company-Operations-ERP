# Payroll Step 5A.2A: migration 005 foundation

Starting checkpoint: clean `fix/payroll-reliability` at `465ad23`. Only migration,
test fixtures/tests and documentation change. No application/repository/template,
salary formula, permission, role grant or production database changes occur.

## Schema contract

Canonical definitions are in `database/migrations/005_payroll_policy.py`.

`payroll_policy_versions` stores the numeric identity, globally unique positive
version number, nonempty name, DRAFT/APPROVED state, positive optimistic revision,
effective date, calculator/calendar identifiers, frequency, cutoff JSON, weekday
mask, pay-type JSON, currency, divisor, rounding mode/scale, five rule documents
(attendance, leave, eligibility, deductions, payment), configuration hash, creation/
update/approval actors, timestamps and optional approval reference.

The first vocabulary explicitly supports the proposed semi-monthly template:
1–15 / 16–MONTH_END, Monday–Friday mask 31, MONTHLY, PHP, divisor 2 and HALF_UP
at two decimal places. Effective dates must fall on day 1 or 16. These constraints
define a supported development template, not formal company salary approval.
Further templates/vocabularies require a reviewed schema/code extension.

Every JSON field has an enforced JSON_SCHEMA_VALID constraint: exact allowed and
required keys, bounded arrays and enumerated values, no additional object keys.
Unknown formulas, script/SQL properties, pay types and payment modes are rejected.
Attendance/leave/eligibility/deduction fields may contain UNRESOLVED in a draft;
approval cannot retain it. BLOCK explicitly represents an unsupported scenario.
Payment configuration supports MANUAL only; no payment dates are invented.

The concrete rule keys are:

| Document | Keys |
|---|---|
| cutoff_rules | a_start, a_end, b_start, b_end |
| attendance_rules | missing_evidence, late_treatment, absence_treatment, half_day_treatment |
| leave_rules | paid_leave_treatment, unpaid_leave_treatment, conflict |
| eligibility_rules | proration, full_cutoff_eligibility |
| deduction_rules | excess_deductions, statutory, odd_cent_handling |
| payment_rules | mode |

These rule values are stored only. No new salary or statutory calculation reads
them in this checkpoint. Supported pay types are the single-item MONTHLY array.

DRAFT rows have NULL approval actor/time/hash. APPROVED rows require a valid actor,
timestamp and 64-character lowercase hexadecimal hash. Hash canonicalization,
calculation and verification remain future service responsibilities: the database
checks syntax and immutability, not whether the hash proves an external approval.

`payroll_policy_activations` uses effective date as its primary key, a unique policy
version reference, activation actor and timestamp. Its composite version/date FK
must match the policy's immutable effective date; actor FKs restrict deletion.
INSERT requires an APPROVED policy, using a locking read. An approved policy alone
does not automatically acquire an activation row.

`payroll_periods` gains NULL `policy_version_id` and ASCII/binary `cutoff_code`
ENUM(A,B). Both must be absent or present together. The FK targets the activation
table's unique version reference. The pair CHECK also rejects the empty ENUM value
that non-strict MySQL might otherwise coerce from an invalid code. No unique
period/date key is added: cancelled-period replacement remains compatible with
the existing shared-guard overlap rule.

## Indexes, foreign keys and triggers

- Version PK; unique version number; unique `(policy_version_id,effective_from)`;
  `(status,effective_from)` index; indexes/FKs for each actor.
- Activation date PK; unique version; composite version/date index/FK; actor index/FK.
- Period indexes `(policy_version_id,start_date,end_date,status)` and
  `(start_date,end_date,status)`; activation-version FK. All new FKs use RESTRICT
  on UPDATE and DELETE.
- `ppv_before_insert`: only DRAFT may be inserted, preventing direct approved INSERT.
- `ppv_before_update`: approved rows reject all updates; draft identity/version/
  creator/creation time remain fixed; revision must increment exactly once.
- `ppv_before_delete`: approved rows cannot be deleted.
- `ppa_before_insert`: referenced policy must be APPROVED.
- `ppa_before_update` / `ppa_before_delete`: activation history is immutable.

A legitimate DRAFT-to-APPROVED update remains possible with revision+1, resolved
rules and complete approval metadata. Database protections also reject common
REPLACE/upsert mutation paths. DRAFT deletion has no application route here.

Active/scheduled/superseded states and half-open effective intervals remain derived
future service concerns. The foundation enforces matching dates and uniqueness;
it does not yet implement future-date scheduling, append-order checks, coordinated
activation, or checks against periods already generated. No activation API exists.

## Safety and preservation

The migration requires compatible InnoDB prerequisites, migration 004 evidence
columns and the existing guard row. It checks critical existing identifiers,
money/evidence types and period keys/date checks/actor FKs. It compares the complete
new-table column sets, indexes, FKs, enforced CHECK expressions, collations and
trigger bodies/SQL modes. Existing unrelated period columns are retained. No new
permission registration is needed for this database foundation.

All legacy references stay NULL. No compensation snapshot, payroll entry, evidence
hash, APPROVED/PAID history, audit row or permission grant is rewritten. Existing
application behavior with NULL references deliberately remains unchanged, including
its present salary formula and legacy payment safeguards. Later policy enforcement
must be deployed across all relevant writers/finalization paths together.

The existing guard is not recreated or changed. Migration DDL is coordinated with
a separate advisory lock because DDL implicitly commits and cannot be protected
as one ordinary business transaction. A maintenance window is still required.
See the migration README for explicit manual execution and interrupted recovery.

Direct database writers should use strict SQL mode. Existing MySQL behavior such
as truncating oversized VARCHAR input in a non-strict session is not a substitute
for the server-side form/repository validation required when policy routes are
implemented. The tested non-strict protection covers immutable history, JSON,
metadata checks, foreign keys and invalid cutoff codes. An unrestricted DBA can
drop triggers/constraints or restore data; this migration does not claim otherwise.

## Verification

`tests/mysql_payroll_policy_schema_smoke.py` starts a fresh temporary MySQL server,
verifies its datadir and uses synthetic records only. It checks fresh/repeated
installation, missing/broken 004 prerequisites, incompatible columns/indexes/FKs/
checks/triggers, unexpected owned objects, migration-lock contention and recovery
from actual partial DDL. It checks strict and non-strict constraint behavior,
first approval, unresolved rules, immutable approved/activation rows, direct SQL,
actor/date integrity, duplicate versions and invalid cutoff codes. Legacy records
and permission/audit tables are compared before/after. Real existing calculation,
return/submit/approve/pay and audit behavior is exercised after upgrade.

Payroll freshness, monetary and period-invalidation suites now explicitly apply
004 and 005 on their disposable fixtures before their existing business checks.
Unit coverage verifies import isolation, caller-transaction protection, bounded
JSON and expression-grouping preservation in metadata comparisons.

No browser/UI implementation is included; configuration UI and authorization,
approval/activation services, calculator dispatch and business-policy decisions
remain for later checkpoints.

## Checkpoint verification results

- Complete Python suite: 292 tests passed; JavaScript suite: 11 tests passed.
- All 21 disposable MySQL smoke suites passed: new policy schema; Payroll
  freshness, monetary and period invalidation (with 005 installed); security;
  central audit; Finance payment, validation, reporting and audit; stock;
  Inventory master and reporting; Procurement; receiving; IT authorization;
  IT lifecycle, validation, audit, reporting and category validation.
- 103 Python files and 104 Jinja templates compiled. Dependency consistency,
  JavaScript syntax and diff checks passed. SQL definitions and triggers executed
  successfully on actual MySQL 8.0.46, including strict/non-strict tests.
- No requested regression suite was unavailable. Browser tests were not part of
  this database-only checkpoint and were not rerun.

Files: `database/migrations/005_payroll_policy.py`,
`database/migrations/README.md`, this document,
`tests/test_payroll_policy_migration.py`,
`tests/mysql_payroll_policy_schema_smoke.py`, `tests/payroll_schema_helpers.py`,
and the existing `tests/mysql_payroll_freshness_smoke.py`,
`tests/mysql_payroll_monetary_smoke.py`,
`tests/mysql_payroll_period_invalidation_smoke.py` fixture upgrades.

Implementation clarifications beyond the original high-level proposal: concrete
bounded rule vocabularies and first-template identifiers, ASCII/binary cutoff
codes, exact revision increments, and additional draft-insert/approved-activation
triggers. No new business calculation, policy assignment or role grant results.
