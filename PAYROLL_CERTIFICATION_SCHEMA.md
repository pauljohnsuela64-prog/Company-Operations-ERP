# Payroll Step 5B.3A — certification evidence schema

Database-only implementation on `fix/payroll-reliability`, starting at clean
checkpoint `7421469`. No certification routes/UI, new salary formula, version-2
calculator or finalization cutover is implemented. In particular, payment of
valid version-1 APPROVED payroll is still governed by the existing application;
the proposed additional payment block has not been authorized or implemented.

## Schema contract

`database/migrations/006_payroll_certification.py` adds four InnoDB tables with
explicit utf8mb4 collation, plus a nullable unsigned BIGINT
`payroll_entries.current_calculation_evidence_id`. Existing 004 version/hash
columns, snapshots and period/policy references remain unchanged. No records,
permissions, grants or historical evidence are seeded/backfilled.

The migration manifest is the exact definition of all columns and constraints.
There are 24 declared indexes (including four primary keys), 16 restrictive
foreign keys, 27 CHECK constraints and 16 protection triggers.

### payroll_cutoff_certifications

Stores unsigned BIGINT certification identity; signed INT period/policy references
matching the existing schema; unsigned revision and nullable predecessor; cutoff
code and inclusive dates; explicit roster scope; authoritative roster/calendar
references; bounded calendar configuration; source/configuration/certification
digests; certification format version 1; ASSEMBLY/SEALED state; creating and
certifying actors with microsecond timestamps. Actor times are explicit inputs;
the future repository must supply authenticated actors and UTC timestamps.

Unique keys cover period/revision and non-NULL predecessor, preventing revision
forks. A composite certification/period identity supports evidence foreign keys.
The policy FK targets existing activations, not an unactivated draft policy.

INSERT locks the period, requires an exact match of its non-NULL policy, cutoff
code and dates, and permits only ASSEMBLY. Initial revision is one with no
predecessor. Further revisions must extend the latest SEALED revision of that
same period by exactly one. Identity/creation fields cannot be rebound during
assembly. The unique keys and predecessor FK remain authoritative safeguards.

### payroll_certification_members

Composite primary key: certification/employee. Stores INCLUDE/EXCLUDE,
UNRESOLVED/FULL_CUTOFF/NOT_ELIGIBLE eligibility, UNVERIFIED/VERIFIED status,
exclusion reason/reference, nullable hire/status snapshots and employment
coverage/reference, compensation identity/rate/pay type/currency and effective
coverage/reference, schedule evidence and material-source digest.

Nullable fields allow unknown historical evidence to remain unknown. EXCLUDE
requires a nonblank reason and reference. Included unresolved members can be
assembled but cannot be sealed. Compensation/employee composite ownership uses
an additional unique parent index and RESTRICT FK. Rates retain DECIMAL(12,2).

The declared roster is an explicit, unique array of positive employee IDs, up to
100,000. Sealing checks equality between that declared population and membership:
matching count and no stored employee outside the declared set. This does not
prove that the declared population itself matches the authoritative HR source.

### payroll_certification_events

Append-only unsigned BIGINT identity, certification, CERTIFY/REVOKE/INVALIDATE/
SUPERSEDE type, optional replacement, actor, microsecond timestamp, nonblank
reason/reference. Certification/type is unique. SUPERSEDE must identify its
actual sealed successor; other events cannot carry a replacement.

Sealing automatically inserts CERTIFY and, for a replacement revision,
SUPERSEDE through an AFTER UPDATE trigger. These are required business records
in the same SQL statement/transaction. Future repositories must not insert
duplicate seal events. REVOKE/INVALIDATE are explicit append-only insertions;
they never mutate sealed headers or reactivate older revisions.

### payroll_calculation_evidence

Append-only unsigned BIGINT identity, evidence version 2, period/entry/employee,
certification, positive calculation sequence, JSON input/output envelope,
rounding-contract identifier, digest and calculating actor/timestamp.

The envelope requires exactly `format_version: 2`, `inputs` object and `outputs`
object, with a 1 MiB JSON storage bound. Business-specific nested fields and
canonical serialization must be defined and validated before a calculator uses
this envelope. This schema does not implement or approve a rounding formula.

Composite FKs bind evidence to the same entry/period/employee and the same
certification/period/member. Evidence insertion requires SEALED INCLUDE membership
and rejects certificates with REVOKE, INVALIDATE or SUPERSEDE events. Sequence is
unique per entry. No evidence UPDATE/DELETE is allowed.

The nullable entry pointer references evidence owned by that entry. Triggers
also require matching period, employee, version 2 and digest. Version 2 requires
its pointer, while legacy NULL/version-1 records retain NULL pointers. The FK
cycle is installed safely: add parent indexes/pointer, create evidence, then add
the pointer FK. No foreign-key checks are disabled.
Future DRAFT invalidation must clear this pointer in the same UPDATE as the
version/hash; retain the immutable evidence rows. Existing writers only produce
version 1 today and need coordinated updates before version-2 calculation begins.

## Assembly, sealing and immutable history

All member mutations lock the header and require ASSEMBLY. Member identities
cannot be moved to another employee or certification. Sealed headers and members
cannot be updated/deleted, and no further members can be added. Unpublished
assembly records can be corrected or removed subject to their FKs.

Sealing requires exact declared membership and VERIFIED dispositions. INCLUDE
additionally requires FULL_CUTOFF, known qualifying hire date, employment/rate
coverage spanning the cutoff, supporting references, MONTHLY/PHP compensation,
and matching schedule arrays. Unsupported calendar/schedule exceptions prevent
sealing. Known exceptions can still be represented in unresolved assemblies.

Calendar JSON is restricted to Asia/Manila, weekday mask 31, unique date-shaped
scheduled-date strings (maximum 16), and bounded typed exception records with
source references (maximum 1,000). Actual calendar dates and weekday completeness
remain application checks. Shape-valid JSON or a SEALED database row is not by
itself proof of authentic employment, calendar or compensation evidence.

Period policy/cutoff/date identity cannot change once certification exists.
History foreign keys use RESTRICT, never CASCADE. Existing unrelated period
state transitions and version-1 calculations/payment remain functional.

Select the highest SEALED revision first, then inspect its events. Never query
for the highest *unrevoked* revision, which could fall back to an older record.
An ASSEMBLY successor does not supersede its predecessor until sealed. The entry
pointer means recorded calculation evidence, not unconditional payment authority;
Step 5B.3B must revalidate current certification and all live material sources.

## Deliberate implementation refinements

- Required CERTIFY/SUPERSEDE records are generated atomically by the seal trigger,
  rather than relying on a future second repository call. A late event failure
  rolls back both sealing and earlier event inserts. This is separate from the
  central best-effort Audit Logs, which are unchanged.
- New digests use ASCII/binary VARCHAR(65), with exact length-64 and lowercase-hex
  checks. A 65-character storage sentinel ensures overlength input cannot become
  a valid digest through non-strict truncation to CHAR(64). Existing 004 hashes
  remain CHAR(64) and are not altered.
- No active-certification pointer or mutable revocation flag was added. Immutable
  revision chains and terminal events preserve history without automatic fallback.
- The version-2 payload is a bounded envelope, not a premature salary-input
  vocabulary. Its complete canonical contract remains a later implementation.

## Migration operation and recovery

006 imports the unchanged sibling 005 module's metadata comparison helpers,
without running its upgrade. Retain both files together. It verifies compatible
004/005 columns, indexes, enforced checks, FKs, protection triggers and the guard
row; expected referenced IDs/types/engines; and enabled FK/unique checks. MySQL
8.0.17+ is required; testing uses MySQL 8.0.46. MariaDB is not supported.
Pre-existing version-2 rows without compatible pointers are rejected before DDL,
never automatically assigned fabricated historical evidence.

All existing owned objects are preflighted before DDL. Unexpected owned tables,
columns, indexes, constraints or triggers, changed definitions/modes, and custom
period/entry triggers require manual review. The script never drops/replaces an
incompatible object. Missing compatible additive stages can resume, including
the final evidence FK and triggers. It restores the migration session SQL mode.

The explicit CLI requires host, port, user and database, prompts for the password,
does not read `.env`, and never connects on import. A database-specific advisory
lock serializes 006 invocations. Use a fresh migration connection; pending
business transactions are rejected. Nothing runs automatically on app startup.

Only after separate operational approval, an authorized operator must:

1. Verify the exact target and backup/restore, and review 004/005 prerequisites.
2. Pause writes from every participating worker/import/direct-SQL process.
3. Review privileges and trigger DEFINER requirements, then run the explicit CLI.
4. Verify completion before restoring writes. Future certification/cutover code
   and coordinated employee/compensation writers require their own deployment.

Example only; this task authorizes disposable testing, not an actual upgrade:

```powershell
.venv\Scripts\python.exe database/migrations/006_payroll_certification.py --host HOST --port 3306 --user MIGRATION_USER --database DATABASE
```

MySQL DDL implicitly commits and may wait for metadata locks. An interrupted
upgrade can leave additive objects committed; an exception is not atomic DDL
rollback. Keep writers paused, investigate, and rerun the unchanged script after
approved resolution. Do not automatically drop evidence or constraints to roll
back application code. The migration advisory lock does not pause business
writers or coordinate different migration numbers.

Triggers execute with their DEFINER privileges. Retain the required account and
SELECT/INSERT privileges; creation may need DBA approval on managed/binary-logged
servers. No global trust, privilege or FK settings are changed by the script.

## Step 5B.3B requirements and database limits

The future repository must validate authoritative roster completeness, external
references, real/full scheduled dates, eligibility, full compensation coverage,
canonical digests, exact bounded policy support and applicable actor permissions.
It must acquire the Payroll guard before existing row locks, reject stale
revisions, inspect revocation/supersession without fallback, and coordinate all
material employee/compensation/calendar/roster/source writers. Direct SQL and old
workers that bypass coordination cannot provide those guarantees.

CHECKs and triggers do not authenticate external evidence or calculate canonical
SHA-256 payloads. MySQL numeric/text coercion can occur before constraints; future
input handling must validate raw Decimal precision, lengths and identifiers before
DML and use approved strict sessions. The digest sentinel specifically closes
digest truncation; it is not a general raw-input validation replacement.

The new version-1 APPROVED payment block remains explicitly unauthorized. No
006 trigger imposes it. No statutory formula, snapshot refresh, employment
history repair or salary policy was introduced.

## Verification and files

New files: this document, `database/migrations/006_payroll_certification.py`,
`tests/test_payroll_certification_migration.py`, and
`tests/mysql_payroll_certification_schema_smoke.py`. The migration README links
this contract. Application code and migrations 004/005 are unchanged.

The disposable schema suite covers fresh/repeated application; committed DDL
interruption and recovery; missing FK/check/trigger restoration; prerequisite,
disabled-integrity-check and advisory-lock rejection; incompatible metadata;
assembly/seal/immutability; explicit exclusions; duplicate revisions/members/
sequences; ownership and restrictive FKs; invalid digest/JSON in strict and
non-strict modes; required-event rollback; and historical data/grant preservation.
It also completes an actual old application calculate/submit/approve/pay workflow
after 006, proving unchanged valid version-1 payment eligibility.

Tests always initialize a new temporary MySQL datadir, verify its actual path,
and use synthetic records only. No company database is accessed. Full Python,
JavaScript and cross-module MySQL regressions are reported in the final review.
There are no new browser workflows in this database-only checkpoint.

Final verification: 313 Python tests and 11 JavaScript tests passed. All 23
existing disposable MySQL smoke suites passed (Payroll, Finance, Procurement,
receiving, Inventory, IT/Help Desk, security and audit), plus the new 006 suite:
24 suites total. The new suite also observes two simultaneous InnoDB waiters
before allowing competing revision inserts; exactly one successor is created.
It rejects unowned pre-existing version-2 rows before DDL and tests both changed
column types and changed trigger bodies without destructive repair. Compilation
passed for 113 Python files and 109 Jinja templates; dependency, JavaScript
syntax and diff checks passed. Browser checks were not run for this schema-only
change. Production deployment and Step 5B.3B remain separate approval checkpoints.
