# HR Step 3.2A: database foundation only

Migration 009 depends on compatible migration 008 (Employee and Department signed
BIGINT revisions, enforced positive CHECKs, and existing identity constraints).
It neither imports nor depends on paused Payroll migrations 004–007. No Payroll
branch has been merged or imported. Migration numbering alone is not a dependency
chain. Future combined-branch deployment still needs an explicit compatibility
review; this checkpoint does not certify unseen branch changes. Read-only inspection
of migrations 004–007 at the preserved Payroll checkpoint found separate Payroll
tables/column targets and no lifecycle-table, flag or trigger name collisions. They
were not imported, executed, or included in this branch's runtime verification.

There are no lifecycle routes, repositories, publication functions, UI, scheduled
activation, permission registrations, role grants, central audit writes, or changes
to existing Employee update methods. Fresh installations also explicitly run 009
after the existing core schema/008; core_schema.sql is intentionally unchanged.

## Tables and identities

All three tables use InnoDB and utf8mb4_bin. Numeric primary keys are local database
identities. Every Employee/User reference is restrictive; no history deletion
cascades are introduced. Same-Employee composite FKs protect optional period,
originating request, and correction references.

* `employee_employment_periods`: unique `(employee_id, period_sequence)`;
  positive sequence/publication revision; verified start DATE; nullable
  end-exclusive DATE strictly after start; boolean void projection; UTC creation
  timestamp. Periods are mutable projections, not the authoritative audit trail.
  Referenced periods cannot be deleted. No one-open-period or overlap restriction
  is imposed. A period publication revision can recur across projections; the
  authoritative unique publication identity belongs to events.
* `employee_lifecycle_requests`: immutable proposal, source, captured positive
  Employee revision, submitting actor and database-set UTC submission time.
  A request begins `PENDING` and permits one terminal metadata decision
  (`APPROVED`, `REJECTED`, `CANCELLED`) with required actor/reason and database-set
  UTC decision time. All proposal columns remain immutable. Terminal rows cannot
  be updated, even to the same values. Requests cannot be deleted.
* `employee_employment_events`: append-only history; unique
  `(employee_id, publication_revision)` and `request_id`; optional period and
  correction reference, required recorded actor/source/reason, optional approval
  actor, database-set UTC recorded time. A unique superseded-event ID permits
  only one direct correction successor; a successor must reference an existing
  same-Employee event with a strictly smaller publication revision. `CORRECT`
  and `VOID` require such a reference; other types cannot carry one. A correction
  chain appends rows and cannot cycle or overwrite its predecessors.

Event/proposal vocabulary is HIRE, STATUS_CHANGE, RESIGN, TERMINATE, REHIRE,
TRANSFER, POSITION_CHANGE, CORRECT, VOID, LEGACY_OBSERVATION. These are structural
labels, not approved transition eligibility rules. Effective DATE plus a positive
ordering number enables later deterministic `(effective_date, effective_order,
publication_revision)` ordering without deciding same-day business precedence.
Payload version is exactly 1; JSON must be an object with serialized UTF-8 length
at most 16,384 bytes. This validates shape/size, not business field semantics.
Source type/reference/version/reason lengths are 30/255/50/255 characters;
version is optional, other fields required and nonblank. TEXT with enforced
length CHECKs avoids VARCHAR silent truncation in non-strict mode. Numeric/date
input still needs explicit application validation before future publication:
database coercions cannot establish business truth or source authenticity.

Six BEFORE triggers implement insert timestamps, immutable proposals, single
terminal decisions, append-only events, and correction direction. This deliberately
uses three tables: retaining both the untouched proposal and its single immutable
terminal decision avoids a fourth decision-history table. Reopening/re-review is
not supported; any future multi-stage review design needs separate approval and
potential additional append-only decision records. No independent-approval or
self-approval rule is selected here. An event's request FK establishes provenance,
not approved source truth, payload equivalence, or authorization to publish.

## Legacy and revision contract

009 adds only `employees.lifecycle_managed TINYINT(1) NOT NULL DEFAULT 0` and an
enforced boolean CHECK to the existing tables. It does not UPDATE Employee rows,
increment revisions, change statuses/departments, synthesize HIRE dates/events,
create periods/requests, mark anyone verified, or inspect real company data.
Compatible existing flag values are preserved on rerun; no automatic repair occurs.
The flag is not a substitute for verified evidence, and existing routes do not
read it. New history references retain Employees and acting Users against deletion.

Future publication must use one coordinated transaction: lock Employee before
dependent history rows; verify the captured revision; validate approved source and
transition rules; append event; update period projection/current Employee state;
increment Employee revision exactly once with the existing compare-and-set
contract; commit all changes together. Neither triggers nor this migration perform
that publication. Required immutable employment history is distinct from optional,
best-effort central Audit Logs. Future central audit runs only after business commit.

## Deliberately deferred decisions

* Whether entered separation date is last employed day or first non-employed day.
  Storage is `[verified_start_date, end_exclusive_date)` and permits either later
  approved mapping; no user-facing mapping is implemented.
* Transition eligibility, same-day ordering/rehire, overlapping periods, backdated
  corrections, verification authority, source retention and independent approval.
* Future activation, synchronization, account offboarding, Attendance/Leave/IT
  eligibility, employment entitlements and all Payroll integration.
* Proposed future permission identifiers: `employees.lifecycle.view`,
  `employees.lifecycle.propose`, `employees.lifecycle.approve`,
  `employees.lifecycle.correct`. These are documentation only. Seed registration
  currently grants all registered permissions to Super Admin, so registration and
  role mapping require a separate reviewed checkpoint.

## Operator safety and compatibility

Development-only checkpoint: do not run against company databases. Approved future
deployment needs a backup, coordinated maintenance window, reviewed DB grants and
trigger definer, and explicit target selection. There is no dotenv loading,
import-time connection, automatic migration runner, or implicit database choice:

```powershell
python database/migrations/009_hr_employment_lifecycle.py --host <host> --port <port> --user <operator> --database <reviewed-target>
```

Password is prompted. Require MySQL 8.0.16+ with enforced CHECK support; MariaDB is
not supported. Run outside any existing transaction. Preflight validates all
existing objects before DDL: 008 contracts, User identity, existing identity FKs,
flag, table columns/defaults, full indexes, same-database restrictive FKs, enforced
CHECK expressions and trigger bodies. Unknown/incompatible lifecycle definitions
fail closed; do not drop/rewrite them automatically. Case and expression grouping
are retained when comparing CHECKs. Metadata formatting differences on another
MySQL version may require a reviewed compatibility adjustment, not bypassing checks.

MySQL DDL implicitly commits: this is not an all-or-nothing schema upgrade.
Compatible missing whole tables, missing triggers and a flag-only additive
interruption can resume. Partially altered existing tables with missing constraints
are rejected because CREATE TABLE is atomic; manual review is needed. Freeze all
writes throughout deployment and recovery so no new rows enter a table before its
immutability triggers exist. No historical evidence is repaired or fabricated.
Reruns preserve current rows and validate definitions. Rollback does not DROP
history; application rollback and DB restore need separate reviewed procedures.

Table privileges and trusted DBA access remain security boundaries: administrators
can DROP/TRUNCATE tables or triggers. Row triggers do not protect against DDL or
disabled FK/CHECK enforcement. No production-scale performance claim is made.
Indexes cover identities/FKs; future report/query shapes need measured indexing.
JSON/text limits are technical bounds, not authorization or privacy policies.

## Verification

`tests/mysql_hr_lifecycle_schema_smoke.py` starts its own isolated MySQL datadir and
loopback port. Synthetic direct SQL verifies fresh/repeated/interrupted upgrade,
missing 008 rejection, incompatible column/index/FK/CHECK/trigger rejection,
legacy/revision/cross-module preservation, no auto histories, defaults, same-Employee
references, duplicate identities, dates, actors, payload bounds, correction chains,
proposal/decision/event immutability, deletion restrictions and rollback in strict
and non-strict SQL modes. No events are published through application routes.
Unit tests cover inert import/transaction rejection and safe metadata comparison.
Browser verification is unnecessary: no browser-facing behavior changes.
