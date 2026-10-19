# HR reliability migration 008 deployment runbook

Status: proposed operator procedure; code approval is not deployment approval.
Do not execute against a company database without separate explicit authorization.
Migration 009, Payroll migrations 004-007, lifecycle publication, offboarding and
permission changes are outside this rollout.

## Compatibility contract

`schema_compatibility.py` defines manifest `erp-main-hr-revisions-v1`:

- Explicit selected database identity and compatible MySQL 8.0.16+ (not MariaDB).
- InnoDB for core identity/authorization, Inventory and Procurement transaction tables.
- Employee and Department business columns, identities, defaults, primary/unique
  keys, and the expected Department foreign key (SET NULL delete, restrictive update).
- Both signed BIGINT NOT NULL DEFAULT 1 revisions, without generated behavior.
- Named ENFORCED CHECK (revision >= 1) constraints on both tables. Missing,
  NOT ENFORCED, unexpected revision constraints or different predicates fail.
- Nullable ASCII/ascii_bin CHAR(36) submission IDs and full single-column unique
  indexes from receiving migration 001 and stock migration 002.
- The four IT/Help Desk permission codes from migration 003. Custom role assignments
  remain unchanged; the inspector never grants, seeds or repairs permissions.

This is a capability contract, not a highest-migration-number comparison. It does
not require migration 009 or paused Payroll migrations. Other modules retain their
existing deployment requirements; this inspector is not a full schema-diff engine.
Fresh installations must provision all mandatory module schemas and authorization
codes explicitly before becoming ready. Existing partial-module test/development
schemas are deliberately not considered full application deployments.

## Read-only diagnostics

From the reviewed artifact, with the approved target and operator credentials:

```powershell
.venv\Scripts\python.exe scripts/check_schema_compatibility.py --host HOST --port 3306 --user INSPECTION_USER --database DATABASE
```

The command prompts for a password, never loads `.env`, and applies no DDL/DML.
Exit status: 0 compatible; 1 capability mismatch; 2 connection/inspection unavailable.
Diagnostics name missing capabilities but do not print credentials or connector SQL
errors. Inspect metadata visibility and network settings when status is 2. The
inspector must see required definitions; missing visibility is not compatibility.
Do not expose operator diagnostics as a public HTTP endpoint.

## Gate operation and limits

Every process starts without a compatibility lease. HTTP admission performs its
first preflight before database-backed authorization; importing the application
performs no database connection or migration. `/health/live` needs no database.
`/health/ready` checks connectivity and capabilities and returns 503 until compatible.
Both health endpoints skip authorization loading, including with a session cookie.

All business requests, exports and direct repository connections are guarded.
Unavailable/incompatible requests receive generic HTML or JSON 503 with no-store.
Outage logout retains existing CSRF, local session removal and best-effort auditing;
it never authorizes a business operation. Compatible authentication, permissions,
CSRF and audit semantics are unchanged. A later failed connection also produces
503; after an earlier committed action this response cannot prove noncommit.

Metadata validation is serialized per process and a positive result expires after
2 seconds. Configuration/manifest changes cause a fresh inspection. Every business
connection checks its actual selected database, even on a cache hit. Connectivity
and inspection failures invalidate the lease; known incompatible results have only
a 1-second rejection cooldown, which can delay admission but can never allow a write.
`database.invalidate_compatibility()` explicitly clears the process lease. There is
no environment or testing switch that disables validation. Connections use a
3-second connect timeout and 5-second read/write timeouts (per connector operation,
not a whole-request deadline). Unreachable targets still require connection attempts;
maintenance admission controls should limit traffic during an outage.

The lease allows a bounded stale-metadata interval. It does not lock the schema,
prove every writer's application version, fence external SQL, or make failover to
an incompatible backend safe. Privileged DDL, target changes and failover require
maintenance and worker replacement. Live rolling schema changes are unsupported.
Direct SQL and FK cascades can still bypass application revision conventions.

## Authorized deployment sequence

1. Record explicit target host/database, artifact/build, authorized operator, window,
   communications, acceptance criteria, recovery owner and approved downtime/RPO.
2. Inventory actual VERSION(), table definitions, engines, keys, FK behavior and
   CHECK enforcement; review existing 001/002/003 capability requirements as well
   as 008. Abort on unexplained divergence. Do not auto-convert engines or repair rows.
3. Take a consistent backup and retain approved restore/PITR material. Verify a
   restoration on a separately approved isolated target, including IDs, relationships,
   counts and historical data. Synthetic tests do not establish actual restore ability.
4. Rehearse the exact migration/worker rollout on approved representative staging.
   Record metadata-lock waits, durations, recovery decisions and preserved records.
5. Enter maintenance and stop new business admission. Drain every web worker, job,
   import, integration and administrative writer, including FK-related parent deletes.
   Coordinate readers which may retain metadata locks. Confirm all work has drained.
6. With one authorized operator and an explicit dedicated target, execute:

   ```powershell
   .venv\Scripts\python.exe database/migrations/008_hr_employee_department_revisions.py --host HOST --port 3306 --user MIGRATION_USER --database DATABASE
   ```

   Password is prompted. No application startup or request runs this command.
7. Inspect both tables completely: signed BIGINT NOT NULL DEFAULT 1, correct named
   ENFORCED positive CHECKs, InnoDB, identities/unique keys/FK unchanged, positive
   counters and original records preserved. A one-table upgrade is not success.
8. Run the read-only diagnostic command. Keep maintenance closed unless it exits 0.
9. Replace every application/job worker with the reviewed compatible artifact.
   Confirm build identity, readiness and absence of old writers on every instance.
   Clear/drain old pending requests; old forms must reload rather than auto-resubmit.
10. Run approved read-only smoke checks: login AND dashboard, Employee listing,
    Add/Edit forms, Departments and selectors in Attendance, Leave, Procurement,
    Finance, IT Assets and Help Desk; inspect generic failure behavior and exports.
11. On separately approved synthetic targets/fixtures, verify CRUD, revision increments,
    stale 409, malformed revision 400, inactive Department protection, status no-ops,
    numeric audit metadata, CSRF and revoked/disabled-account rejection. Company-record
    write testing requires separate authorization. Audit delivery remains best effort.
12. Reopen business traffic only after all acceptance criteria pass. Monitor readiness,
    503/1054 errors, conflicts, lock timeouts, latency and audit-storage failures.

## Failure and recovery

Keep maintenance closed on any migration, readiness, restoration or smoke failure.
Each completed DDL statement persists independently; rollback does not undo earlier
ALTER TABLE statements. Inspect interrupted upgrades and rerun 008 only when the
remaining state is compatible. Escalate incompatible definitions; never reset
revision counters, drop protections blindly or invent historical values.

Prefer reviewed fix-forward recovery retaining additive columns/checks. Rolling
back to legacy writers does not preserve concurrency guarantees. Any fallback must
coordinate the maintenance gate and every worker. Never drop revisions with new
workers active or permit mixed legacy/revision-aware workers to write.

A lost commit acknowledgment may follow a real commit. Reconcile persisted IDs,
revisions and transaction evidence before retrying; absence of an audit event is
not rollback evidence. Audit storage cannot reverse a committed business action.
Backup restoration must account for later writes and invalidate pre-restore forms
and reused concurrency evidence. Preserve historical records and existing counters;
migration 008 establishes concurrency baselines, not employment history.

## Verification and future CI

Run Python/JavaScript suites, the disposable schema compatibility matrix, existing
MySQL suites and three Chrome workflows before a checkpoint. The gate matrix must
prove pre-008 valid creates cannot commit, including direct repository callers,
and that all registered business endpoints remain unexecuted while incompatible.

Existing route unit tests explicitly mock readiness just as they mock repositories.
Existing disposable suites retain their scoped connection factories; the dedicated
`tests/mysql_schema_compatibility_smoke.py` instead replaces connectivity only and
executes the real inspector, guard and repository connection gate. No runtime
production bypass exists. Use synthetic data only.

Future GitHub Actions can run Python/JavaScript and disposable MySQL jobs plus
Chrome workflows on suitable runners. Do not claim GitHub CI passed from local
results, and never provide company credentials to these jobs.
