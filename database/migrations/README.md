# Goods receipt duplicate protection

## Standalone HR upgrade 008

`008_hr_employee_department_revisions.py` is an independently invoked HR upgrade,
not a sequential runner step. It has no dependency on unfinished Payroll migrations
004-007. See [HR_REVISIONS.md](../../HR_REVISIONS.md) for explicit targeting,
preflight/repeatability, interrupted-DDL recovery, deployment and rollback limits.
Never run migrations implicitly at application startup. This upgrade requires
MySQL 8.0.16+ and InnoDB; it must be reviewed and applied by an approved operator.

## Receiving upgrade 001

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

# HR employment lifecycle foundation (009)

Migration `009_hr_employment_lifecycle.py` is an explicit development-only database
foundation following compatible HR migration 008. It does not depend on Payroll
004–007, publish events, synchronize Employee state, register permissions, or backfill
history. Fresh installations also run it explicitly. Review
[HR_LIFECYCLE_SCHEMA.md](../../HR_LIFECYCLE_SCHEMA.md) for the full schema, deferred
policies, operator command, preflight/recovery behavior and DDL deployment risks.
Do not apply this checkpoint to actual company databases without separate approval.
