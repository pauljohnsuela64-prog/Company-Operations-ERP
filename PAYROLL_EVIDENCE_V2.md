# Payroll 5B.3C: calculation evidence foundation

This checkpoint adds no salary engine, HTTP route, UI, role grant, finalization
cutover, or migration. `payroll_freshness.py` is unchanged: version 1 still uses
the original projection, Decimal `str`, ISO dates, compact sorted JSON, default
ASCII escaping and SHA-256. Its historical verification/payment rules remain
unchanged. The explicit `fingerprint_for_version` infrastructure dispatcher
supports 1 and 2 and rejects other versions (including booleans/strings). It is
deliberately NOT wired into submission, approval or payment yet.

## Authoritative validation

`payroll_evidence_repository.validate_eligibility(cursor, period_id,
require_entries=True)` runs in the caller's transaction. The caller must acquire
the singleton payroll guard before ANY other lock or source read. The validator
also acquires that guard defensively; calling it after a child lock does not make
an inverted lock order safe. Do not reuse its returned context across commits.

Lock order: guard, period, activation/policy schedule, latest sealed certification,
members/events, current employee/compensation sources, entries in ID order, then
attendance/approved leave (including joined leave types) and adjustments. Existing
participating source writers use the same guard first. Locking current reads,
including certification events and the employee population, avoid a pre-existing
REPEATABLE READ snapshot after a guard wait. No schema or isolation-mode change
is needed.

The period must be pinned to exact A (1–15) or B (16–month end) dates and the
original approved, activated, resolved and hash-valid policy covering that entire
cutoff. Cancelled periods fail. The latest SEALED revision is checked, including
terminal REVOKE/INVALIDATE/SUPERSEDE events; there is no older-revision fallback.
An unsealed correction does not supersede a sealed revision.

Publication validation is reused against current material sources and the
original certifier's authority (not a future payment actor's certify permission).
It verifies every declared roster disposition against trusted external claims,
full employment/rate coverage and references, supported MONTHLY/PHP compensation,
schedule/calendar coverage and no special-day exceptions. The certification seal
and calendar digest are independently checked. Entries must exactly match the
included population and certified compensation snapshots. `require_entries=False`
is exclusively the future pre-generation boundary; existing partial entries are
still checked against certification. Active status or a nonempty reference alone
never supplies entitlement.

Production `authoritative_evidence()` still returns None. Consequently real v2
validation and persistence fail closed, regardless of permissions or a matching
hash. An approved adapter must establish the full authoritative scope, employment
and rate coverage, calendar provenance and certifier authority. A digest proves
content consistency, not authenticity of an HR document. No environment flag or
form payload can enable the adapter. The tests patch it with captured synthetic
claims on explicitly disposable databases only.

Existing 006 certifications sealed before the 007 fields existed may not match
the extended certification digest projection. This foundation fails closed rather
than resealing them. Any compatibility/correction procedure needs separate review;
current production v1 workflows do not use this validator and are unaffected.

## Canonical version 2

`payroll_evidence.py` declares an exact nested schema. Its only envelope keys are
`format_version: 2`, `inputs`, `outputs`, matching migration 006. Inputs bind:

- Inclusive period dates/ID/cutoff, pinned policy ID/version/configuration hash,
  allowlisted calculator and calendar identifiers (never executable configuration).
- Certification ID/revision/digest, certifier and timestamp, source/calendar
  digests and readable source references, complete included AND excluded roster
  with recorded eligibility/compensation references and snapshots.
- Calendar and scheduled dates; entry/employee/compensation identity and snapshot.
- All cutoff attendance statuses (including weekends), ordered overlapping
  approved leave with type ID, paid classification and total days, scheduled-day
  classifications, and ordered earnings/deduction IDs/types/amounts.
- `POLICY_HALF_UP_2_V1`, which binds the existing policy's technical rounding
  configuration; it does not approve or implement a salary formula.
- Seven stored monetary outputs and eight day-count outputs.

Objects use sorted keys, compact JSON, ASCII escaping and SHA-256 of UTF-8 bytes.
Collections have defined ID/date ordering; duplicate identities/scheduled dates
fail. NULL is JSON null only in explicitly nullable member/reference fields.
Money is finite, nonnegative DECIMAL(12,2) serialized as exact two-place strings;
rates/adjustments require positive values. Negative zero normalizes to `0.00`.
Floats, bool-as-number, excess precision, overflow, unknown keys/values, unsupported
engines, exception arrays and malformed dates fail. Dates are ISO YYYY-MM-DD.
Certification DATETIME(6) is written as UTC by the existing repository; evidence
converts it to ISO with explicit Asia/Manila offset and six fractional digits.
No host-local timezone inference is used. Payloads over 900,000 encoded bytes
fail before persistence, below the schema's 1 MiB storage limit; enormous rosters
may need a future reviewed storage design rather than silent omission.

Scheduled weekdays require exactly one attendance row and unambiguous approved
leave. Missing attendance, overlapping leave, ON_LEAVE without approved leave,
leave conflicting with another attendance status, unsupported partial-day leave,
and policy-BLOCK classifications fail. This implements evidence eligibility, not
new leave entitlement or salary arithmetic. The future engine must resolve any
remaining leave-duration semantics and statutory/odd-cent policy restrictions.

## Persistence and freshness

`persist_proposed(period_id, entry_id, outputs, actor_id)` is an internal foundation
helper with NO production caller. Only synthetic fixtures exercise it now. It
opens a guarded transaction, revalidates all sources, accepts explicitly proposed
outputs (never calls the old salary formula), checks exact day counts and
earnings/deduction aggregate identities, inserts append-only evidence, then saves
outputs plus the version/hash/current pointer in the same transaction. Only Draft
periods and DRAFT/CALCULATED entries can be written. Failure, including pointer
failure, rolls back both insert and entry update. Per-entry sequences serialize
under the guard and entry lock. It does not assert that proposed regular/net pay
is a correct salary: that belongs to the future approved calculator. Do not expose
this helper as a form/API that accepts user-proposed salary outputs.

`verify_current(cursor, period_id, entry_id)` revalidates eligibility and ownership,
checks stored version/rounding/digest and the entry hash, rebuilds current evidence
from live locked sources and saved outputs, then compares digests. Changes to
revision/revocation, roster, material employment/rate facts, entry snapshots,
attendance, approved leave/type classification, adjustments, policy/calendar or
outputs fail. Nonmaterial names, contacts, notes and formatting are intentionally
excluded. Evidence does not auto-refresh on source changes.

Migration 006's composite FKs enforce period/entry/employee/certification/member
ownership; append-only triggers protect evidence; the entry pointer trigger binds
owner/version/hash. Application validation supplies the stricter nested contract.
No modification of 004–007, backfill, history repair or new migration is required.
No central audit success event is introduced because no production business action
is added. Existing certification transactional events and postcommit best-effort
central Audit Logs remain intact.

## Future approved integration

1. Entry generation: after guard and period lock, validate with
   `require_entries=False`; use the certified roster/snapshots instead of Active
   employee selection. This selection change is NOT enabled here.
2. Calculation: validate the complete entry population, implement the separately
   approved policy engine, build evidence from its proposed outputs and atomically
   insert/update within that same existing authorized transaction. Refactor the
   persistence helper to accept that transaction rather than nesting transactions.
3. Submission/approval/payment: within the existing workflow repository and its
   existing locks, use explicit version dispatch/`verify_current` only after the
   approved compatibility and finalization cutover. Do not create parallel routes
   or bypass existing permission, CSRF, readiness/state and audit checks.

At present existing workflows remain v1-only; they reject synthetic v2 entries as
unverified. Current old calculation/invalidation code does not clear a v2 pointer;
the database check causes rollback rather than a partial overwrite. The approved
future integration must atomically clear pointer/version/hash when invalidating,
preserving immutable evidence rows. No historical APPROVED/PAID rows are changed.

## Limits and verification

The global guard serializes participating workers and can limit throughput.
Direct SQL, older deployed writers that omit it, or an external authority changing
without transactional/versioned coordination remain operational risks. Row locks
protect read existing rows but cannot make an external document transactional.
Source digests are content checks; changing and reverting identical facts can
match again. Explicit certification revocation remains permanent. Deploy coherent
workers; do not claim direct-SQL or external-system atomicity.

Tests include a frozen v1 digest, strict canonical serialization, supported daily
classifications and ambiguous evidence, synthetic MySQL persistence/rollback,
ownership, source/output/adjustment drift, complete roster, latest corrections and
revocation. Races assert actual `performance_schema.data_lock_waits`, both source
writer→validator and validator→revocation, with post-wait revalidation, plus two
queued evidence writers with distinct sequences and one consistent current pointer.
A population change is also detected despite an earlier REPEATABLE READ snapshot. Existing
freshness/workflow suites exercise historical v1 approval/payment, permissions,
CSRF and coordinated Attendance/Leave races. All DB tests initialize fresh loopback
MySQL datadirs and verify isolation before creating synthetic records.

Browser behavior is unchanged (no routes/templates/JS changes), so Chrome is not
required for this foundation. Future browser checks belong to the approved
calculator/finalization integration, including source failure, revocation/staleness,
normal approved salary workflows, authorization, CSRF and audit failure isolation.

Checkpoint verification (synthetic/disposable only): 328 Python tests, 11 JavaScript
tests and all 26 MySQL smoke suites passed. The expanded evidence smoke was rerun
after the concurrency additions and passed. Compilation passed for 121 Python
files and 114 Jinja templates; JavaScript syntax, `pip check`, tracked diff and
new-file whitespace checks passed. No actual database migration was executed.
