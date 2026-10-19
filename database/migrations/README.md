# Goods receipt duplicate protection

`procurement_schema.sql` includes the new definition for fresh installations.
`CREATE TABLE IF NOT EXISTS` does not upgrade existing tables.

For an existing database, back up the database, pause receiving writes across all
application workers, and have an authorized operator run this explicit migration
before deploying the new application code:

```powershell
.venv\Scripts\python.exe database/migrations/001_goods_receipt_submission.py --host HOST --port 3306 --user MIGRATION_USER --database DATABASE
```

The script prompts for the password; it does not read `.env`, select a database
implicitly, or execute on import. It adds nullable ASCII `CHAR(36) submission_id`
and a full UNIQUE index. Existing receipt rows retain NULL, identifiers, and all
business data. The old application can still insert NULL during a rollback, but
those writes have no duplicate protection. Resume receiving only when all workers
run the new code. MySQL DDL implicitly commits and can wait for metadata locks;
allow a maintenance window appropriate to the table size. No migration is run by
application startup. The upgrade is repeatable, including after an interrupted
column/index upgrade, and rejects incompatible preexisting definitions. It does
not remove historical duplicates or backfill invented tokens.

Use InnoDB for all procurement/inventory tables. Do not remove the new column or
unique index while this application is deployed. Prefer rolling the application
back while retaining this additive schema if rollback is necessary.

Each receiving form has a UUID. The repository requires it and stores it with the
receipt in the same transaction as receipt items, stock, movements, PO status and
PR completion. A PO row lock serializes receiving/cancellation for that order;
a unique index also enforces token uniqueness across orders. Replays compare the
PO, warehouse, acting user, notes, and positive item quantities with the persisted
receipt. An identical replay returns the existing receipt even after full receipt;
changed details with an already used token produce a validation error. Zero lines
are ignored for equality. Authorization still uses the existing receiving
permission. Tokens are idempotency keys, not authorization or CSRF tokens.

Reloading/opening a fresh form generates a new token and intentionally allows a
separate delivery with identical quantities. Thus a user who opens a new form and
manually re-enters the same delivery can still duplicate it within remaining order
quantities. Callers must reuse their original token when the outcome is uncertain;
the application does not deduplicate deliveries by quantity or supplier paperwork.
The same token is preserved on validation errors. Deliberately changed payloads
must use a new form after a successful save. Existing historical receipts cannot
be recognized as retries because they have no token.

Stock reserves or creates each row through an atomic upsert in a consistent item
order, locks it, validates the new Decimal balance, and updates it. Aggregate
overflow is rejected even with non-strict MySQL settings. Deadlocks and
lock timeouts retry the entire rolled-back transaction up to three attempts with
the same token; other connector errors return a user-facing error. Connection
loss at commit may leave the outcome uncertain, so retry with the same token to
resolve it. SQL errors are chained for diagnostics. No receipt writes occur before
numeric validation, and any downstream failure rolls back all receiving changes.

Run the isolated automated checks (each MySQL script starts and verifies its own
fresh temporary server; none connects using company database settings):

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
.venv\Scripts\python.exe tests/mysql_procurement_smoke.py
.venv\Scripts\python.exe tests/mysql_receiving_smoke.py
.venv\Scripts\python.exe tests/mysql_audit_smoke.py
```

Before enabling receiving, manually confirm the target schema's new column/index
and InnoDB engines, apply the migration through the authorized process, and test
in a non-company sandbox: double-click/repost a partial and a full delivery,
retry after a simulated lost response, and then open a new form for a separate
identical partial delivery. Recheck receipt history, warehouse balances and stock
movement references. Do not use real company records for verification.


# Manual Stock In/Out duplicate protection (Inventory Step 2)

Fresh installations use the nullable ASCII `CHAR(36)` `stock_movements.submission_id`
and full UNIQUE index `uq_stock_movements_submission` in `inventory_schema.sql`.
Existing tables are not upgraded by `CREATE TABLE IF NOT EXISTS`.

An authorized operator must perform the following before enabling the new manual
Stock In/Out code. This is never run by application startup:

1. Back up the target database and verify the backup can be restored. Confirm the
   exact target host/database and appropriate MySQL 8.0/InnoDB compatibility.
2. Pause manual Stock In/Out across every worker. Coordinate a maintenance window
   for stock movements, including receiving, because DDL can wait for metadata locks.
3. Record historical movement IDs/counts and stock balances. Rehearse the upgrade
   on a disposable schema, then execute explicitly:

   ```powershell
   .venv\Scripts\python.exe database/migrations/002_manual_stock_submission.py --host HOST --port 3306 --user MIGRATION_USER --database DATABASE
   ```

   The password is prompted, not passed on the command line. The script does not
   read `.env` or choose a database implicitly.
4. Verify the nullable ASCII `CHAR(36)`/`ascii_bin` column and full single-column
   UNIQUE index. Re-run the migration to verify repeatability. Historical rows
   retain NULL and original data; no balances, movement IDs, or reference fields
   are changed. An interrupted column-only upgrade adds the missing index on rerun.
   Incompatible existing columns/indexes fail explicitly; investigate rather than
   replacing constraints or assigning invented UUIDs to historical records.
5. Deploy the matching code to every worker before resuming manual writes. Verify
   retry, concurrency, changed-payload rejection, and Procurement compatibility on
   synthetic data in an isolated test environment. Do not test with company records.

MySQL DDL implicitly commits. Keep the additive column/index during application
rollback; do not drop them while new code is active. Old code can still insert NULL,
but such operations have no duplicate protection. Mixed old/new workers are unsafe
for the new guarantee. A backup/restore rollback must account for all later business
writes; this script does not perform automatic rollback or data cleanup.

Each manual form now requires a UUID. The same UUID must accompany retries,
including expired-CSRF recovery. Identical retries match direction, item, warehouse,
Decimal quantity, normalized blank notes, and actor, then return the original movement
ID. Changed details with the same key are rejected. A new UUID intentionally permits
a separate transaction with identical quantities. UUIDs are not authorization tokens.
The unique index arbitrates cross-item/warehouse collisions; the movement, UUID and
balance change commit atomically. Goods Receipts continue using their separate UUID
column; their stock movements leave this new column NULL.

The returned `StockResult` has `movement_id` and `created`. Future central audit
integration must emit success events only for `created=True`, never for a replay.
No new central audit events are introduced in Step 2.

Run `tests/mysql_stock_smoke.py` for disposable migration/idempotency and mixed
receiving tests. No development or production migration is applied by those tests.


# Payroll calculation freshness (004)

Migration `004_payroll_freshness.py` is additive and repeatable. It validates InnoDB
and existing definitions, adds nullable version/hash evidence without backfilling
legacy calculations, and provisions a shared HR/Payroll transaction-lock row.
No migration runs automatically. See `PAYROLL_FRESHNESS_PROPOSAL.md` for the approved
design, legacy payment restrictions and unresolved salary-calendar policy.

An authorized operator must back up and verify restore, pause Payroll/Attendance/
Leave writes across every worker, and run the explicit upgrade before deploying
all coordinated writers. DDL can implicitly commit/wait for metadata locks; rerun
an interrupted upgrade. Do not remove the additive schema for an application rollback.
Old/mixed workers do not honor coordination and cannot guarantee freshness.

```powershell
.venv\Scripts\python.exe database/migrations/004_payroll_freshness.py --host HOST --port 3306 --user MIGRATION_USER --database DATABASE
```

The script prompts for a password and never reads `.env` or chooses a database
implicitly. Verify the actual target before invoking it. The current development
task authorizes disposable testing only, not an actual company database upgrade.
Legacy APPROVED payment without evidence is blocked; company-approved correction/
verification is required. Historical PAID records remain unchanged.

# Payroll policy schema foundation (005)

`005_payroll_policy.py` is an explicit, additive database upgrade. It requires the
existing 004 columns, compatible InnoDB prerequisites and coordination row; it
does not invoke 004 or repair an incompatible prerequisite. MySQL 8.0.17+ is
required for enforced CHECK constraints and JSON_SCHEMA_VALID. Actual disposable
verification uses MySQL 8.0.46. MariaDB is not supported by this migration.

The upgrade adds two policy tables, six protection triggers and nullable policy/
cutoff references on periods. It verifies existing definitions before applying
DDL and verifies the completed installation. A connection-scoped advisory lock
prevents simultaneous runs of 005; this lock does not pause application writers.
Column definitions, engines, collations, indexes, foreign keys, enforced CHECK
expressions and trigger bodies/modes are checked. Unexpected policy-table objects
or constraints on the owned period columns require manual review. Missing additive
stages can resume after an interruption; incompatible definitions are never dropped
or automatically replaced.

No approved or draft policy is seeded, no historical period is assigned a policy,
and no permission or role grant is inserted. The application permission names
are `payroll.policy.manage`, `payroll.policy.approve`, `payroll.policy.activate`.
The existing permissions table can hold these identifiers without schema changes;
registration is provided separately by `database/payroll_policy_permissions.sql`
for the policy-management checkpoint. That repeatable script inserts catalog
entries only, never role grants, and is not executed on application startup.
An authorized operator must review the target and run it through a controlled
upgrade after schema verification. Review and explicitly assign each role grant
separately; no role, including Super Admin, receives a bypass. See
`PAYROLL_POLICY_MANAGEMENT.md` for deployment and verification requirements.

Only after explicit operational approval: verify the backup/restore procedure and
target, pause Payroll/HR writes across all workers, use a fresh migration connection,
and run:

```powershell
.venv\Scripts\python.exe database/migrations/005_payroll_policy.py --host HOST --port 3306 --user MIGRATION_USER --database DATABASE
```

The script requires explicit connection arguments, prompts for the password, never
reads `.env`, and never connects on import. It must be run by an account able to
inspect metadata and create tables/indexes/checks/FKs/triggers. The target schema
must already contain the existing application schemas and migration 004.
Review the trigger DEFINER account and retain its required privileges. Managed or
binary-logged servers may require an approved DBA to authorize trigger creation;
the migration does not change server-wide trust or privilege settings.

MySQL DDL implicitly commits and can wait for metadata locks. Do not interpret an
exception as an atomic DDL rollback. Record the error, keep writers paused, review
any incompatible object, and rerun the unchanged migration after resolving the
cause through an approved process. No automatic destructive repair is provided.
For an application rollback, retain the additive objects; do not automatically drop
policy history or columns. A backup restore must account for subsequent business
writes. Privileged administrators can bypass/drop database protections; these are
not a defense against unrestricted DBA access.

This checkpoint does not change existing calculation dispatch, approval/payment
logic, fingerprints or legacy NULL handling. Policy-based enforcement requires a
later coordinated code deployment; the presence of these tables does not approve
the proposed development template or enable a new calculator. See
`PAYROLL_POLICY_SCHEMA.md` for the contract, limits and test coverage.
