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
