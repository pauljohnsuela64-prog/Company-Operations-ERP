# Payroll Attendance freshness — development implementation

Owner approval covers development and disposable testing only. No production
rollout, company-data access, recovery workflow or Assignment 3 is authorized.

## Evidence and transaction contract

Every cooperating Attendance, Leave and Payroll writer first locks the single
InnoDB payroll_attendance_guard row in its transaction. Existing schedule,
period, entry and source locks follow it. The guard remains held through commit
or rollback. This deliberately serializes these writers across periods.

Attendance saves advance durable employee/date generations in the same transaction
as the source write. Date/employee moves advance both old and new keys. Tombstones
remain after moves; generations cannot wrap or reset. Accepted no-op saves also
advance conservatively. Effective Leave approval and paid/unpaid Leave-type changes
advance affected weekdays, protecting existing calculation inputs without changing
their classification rules or formulas.

Explicit calculation saves its version, exact cutoff scope and employee/date
generation for every scheduled weekday, including absent rows represented by zero.
Calculation results and evidence commit together. Submit, approve and pay compare
complete saved evidence with locking current reads under the same guard. Timestamp
precision is no longer a freshness authority. Cutoff changes require recalculation.
Out-of-scope source changes do not invalidate a calculation.

Source-first operations are seen by subsequent calculation/validation. Payroll-first
operations finish before a waiting source change; that change invalidates the next
transition. This cannot prevent a later source correction after a completed payment;
PAID history remains unchanged and cannot be recalculated through this workflow.

Lock failures, incomplete structures/evidence, incompatible engines, exhausted
generations and stale/unknown evidence fail closed. There is no transaction replay,
automatic recalculation, automatic reopening or payment bypass. Lost commit
acknowledgments require explicit reconciliation with persisted state.

## Schema and migration

MySQL 8.0.16+ with enforced CHECK constraints and InnoDB is required. Fresh schema
files contain the guard, generations, snapshots and three nullable evidence/scope
columns. Existing installations require explicit migration 010; runtime/import and
readiness inspection never create or repair these structures.

Schema admission is shared across the application. Missing or incompatible
freshness structures can therefore make database-backed requests, including login,
temporarily unavailable, rather than affecting Payroll writes alone. Plan a drained
maintenance window; do not start new workers against an unmigrated database. The
bounded admission lease is not permission to run mixed application versions.

The migration requires explicit host, port, user and database and prompts for a
password. It does not read application connection defaults. For this approval,
execute it only inside the verified synthetic disposable harness. It preflights
existing structures, supports partial/repeated installation, preserves generations,
and never backfills business evidence or modifies amounts/statuses/history.
Optional Attendance/Payroll business tables are not installed by the migration.
MySQL DDL implicitly commits; partial failure requires operator inspection and an
explicit rerun, not an assumed transactional schema rollback.

Before any separately approved rollout: take and verify backups, stop all
participating writers, inspect the target/version/engines, apply and verify the
additive migration, deploy every cooperating worker, and verify readiness before
resuming writes. Mixed old/new workers and direct SQL writers bypass the guard
contract and are unsupported. Keep additive structures during application rollback;
rolling back to old writers loses this integrity guarantee. No automated rollback,
production migration or destructive cleanup is supplied.

## Legacy and APPROVED recovery proposal

Existing NULL evidence remains unknown. DRAFT must be explicitly calculated;
PROCESSING requires the existing authorized return-to-Draft action followed by
explicit calculation and submission. All existing validation/permission rules apply.
Stale or unknown APPROVED payment is blocked without reopening or modifying the run.
PAID records remain readable and unchanged.

Proposed recovery, requiring separate owner approval before implementation:

1. Hold the affected payment and reconcile persisted status, audit history, source
   changes and any uncertain payment acknowledgment; establish whether money moved.
2. Have authorized Payroll/Finance reviewers document the discrepancy and approve
   an explicit correction path, including separation of duties and audit evidence.
3. Separately design and approve either controlled reopening of an unpaid APPROVED
   run or a replacement/correction run. Specify reference handling, recalculation,
   resubmission and fresh approval before implementing any workflow.
4. Handle already-paid discrepancies under a separately approved correction/reversal
   policy. Never overwrite PAID history or fabricate snapshots to unblock payment.

No new recovery endpoint, status transition, permission grant or policy is included.

## Evidence and limits

The unchanged original audit, 15 regression scenarios, sixteen ordered source/Payroll
races under REPEATABLE READ and READ COMMITTED, actual 1205/1213 failures, uncertain
commits, Leave changes, migrations and real Chrome workflows cover this contract.
See ERP_V1_CLEANUP_REPORT.md for exact final results. Synthetic concurrency proves
ordering, not production throughput. Guard contention, production sizing, external
writer inventory, deployment/backup rehearsal, recovery policy and existing salary
policy acceptance remain unverified or require owner approval.
