# Warehouse reliability and usability

The Warehouse feature keeps the existing `inventory.view` listing permission,
`inventory.warehouses.manage` mutation permission, authentication refresh, CSRF
protection and schema compatibility gate. It adds no schema, grants, inventory
calculations, stock-holding restriction, or historical data rewrite.

## Listing and validation

`/inventory/warehouses` accepts `search`, `status` (empty, active, inactive),
`page` (positive ASCII integer through 2147483647), and `page_size` (25, 50, 100;
default 25). Unknown, duplicate and malformed filter values return 400 rather
than silently broadening a query. Search is bounded to 100 characters and matches
code, name or location using bound parameters. `%`, `_` and `!` are literal.
Database collation still determines case/accent comparisons. Clear resets filters;
page-size/filter submission resets to page one; page links retain filters.

Count and rows use one InnoDB READ ONLY REPEATABLE READ snapshot. The count includes
all filtered historical records. Rows sort by warehouse name then ID; out-of-range
pages clamp to the last page. Empty database, empty filtered results and unavailable
loads have separate messages. No listing request commits or writes business data.
`get_all_warehouses()` stays unbounded for existing inventory/receiving consumers,
with ID added as a stable secondary sort key; only the listing uses the page API.

Repository validation runs before writes in strict and non-strict SQL modes.
Code is trimmed/uppercased (30 characters); name trimmed (100); location optional,
trimmed (255). Invalid Unicode and controls are rejected. IDs must be positive
32-bit integers. No new character whitelist, naming policy or employee restriction
is imposed. Existing unique code/name indexes arbitrate concurrent duplicates;
errors retain escaped submitted values without exposing SQL. Input errors return
400; duplicate feedback retains the existing 200 form-response contract.
Missing rows are reported, not silently updated. Add/Edit templates already retain
values and include CSRF tokens; those behaviors are reused.

## Transactions, status and stock

Create/Edit/status writes use explicit transactions; edit/status lock the warehouse
row. An identical edit or desired status is a no-op without a success audit or
updated timestamp. Failed SQL rolls back; an unconfirmed write returns 503 and
asks the operator to refresh/reconcile, never automatically replaying the action.
A commit acknowledgment/cleanup failure may follow a real commit: do not assume
503 means rollback. Reconcile business state and logs before retrying.

New status forms submit an explicit target boolean, so repeated same-target
submissions are no-ops. Legacy forms without a target retain the prior toggle
contract. Direct repository callers still receive booleans from status updates;
`update_warehouse()` now returns whether data changed (previously returned None).
Existing production callers were reviewed and the Warehouse route consumes it.
Create still returns the numeric ID only after its commit completes.

Stock movements already hold a shared warehouse eligibility lock. Goods Receiving
now does the same through its existing transaction. Deactivation waits for an
admitted movement/receipt to commit; a later writer sees inactivity and rejects
under the existing rules. Deactivation remains allowed when stock exists. No stock,
movement, receipt, or foreign-key history is deleted or recalculated. The only
Procurement production change is the shared lock on warehouse eligibility.

## Auditing and limitations

Confirmed changed writes attempt CREATE, UPDATE, ACTIVATE or DEACTIVATE through the
existing central best-effort helper. IDs are numeric, module INVENTORY, entity
WAREHOUSE. Names/locations are excluded. Create/Edit descriptions retain the code;
status descriptions use ID alone so a concurrent rename cannot give a stale label.
Failed/no-op writes emit no success event. Audit storage failure cannot reverse a
confirmed Warehouse commit. Delivery is not durable, exactly-once or tamper-proof.

Stale edit forms can still overwrite later edits; no revision migration is added.
Explicit status targets are not revision checks; older forms still toggle and are
not idempotent across sequential retries. Separate pages may shift during concurrent
changes. Full counts, LIKE searches and deep offsets need production performance
qualification. External/direct SQL or legacy workers can bypass these application
locks/conventions. Use compatible workers during a controlled rollout. There is
no company deployment approval, migration execution or automatic production action.

## Verification

See [tests/README.md](tests/README.md) for commands. Unit tests block company DB
access; SQL and Chrome fixtures use only the existing verified disposable MySQL
launcher and synthetic records. Chrome runs separately from hosted CI. Green local
or CI checks do not authorize company database operations or deployment.
