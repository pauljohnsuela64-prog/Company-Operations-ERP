# Inventory Step 3: master-data validation

Started on feature/inventory-improvements at 94ff165 with a clean working tree.

## Validation and reliability

Repository validation covers both create and edit, including non-HTTP callers:

| Master | Required fields / maximum characters | Optional fields |
| --- | --- | --- |
| Category | code 30, name 100 | description 255 |
| Warehouse | code 30, name 100 | location 255 |
| Item | code 50, name 150, unit 30 | description 255; nullable category |

Text is stripped; codes retain existing uppercase normalization. Reorder levels
use Decimal, allowing zero through 9999999999.99 with at most two decimal places.
NaN, Infinity, negative values, excessive precision and overflow are rejected.
Routes display validation errors and retain existing duplicate-code/name handling.
No migrations, new audit events or balance/history updates are introduced.

Malformed category IDs fail before a write connection is opened. Item creation
checks category existence/activation under a shared row lock inside its write
transaction. Item editing first locks the current item, then validates the category
assignment against the current persisted assignment. A previously assigned inactive
category can be retained while editing; a new assignment to an inactive category is
rejected. The dropdown offers active categories plus the current inactive category.
Categories remain optional, matching the existing schema.

Category, warehouse and item updates revalidate existence under a row lock, so a
record disappearing after the route lookup cannot result in a false success.
Unique constraints arbitrate concurrent duplicate codes/names; rejected writes roll
back. Category deactivation waits for an in-flight assignment's shared lock; if
it commits first, the new assignment is rejected.

## Policy recommendations requiring approval

- Unit changes after the first stock movement: recommend preventing direct unit
  changes and requiring a separately approved conversion/correction process. Today
  unit edits remain allowed, and history screens use current master labels. This
  restriction is not implemented in Step 3.
- Existing inactive categories: keep existing assignments editable and permit
  moving to an active category or no category. This retention behavior is preserved;
  only new inactive assignments are rejected. Treat category activation as an
  assignment policy, not an implicit freeze of every existing item's stock.
- Deactivation with stock: recommend a stock-clearance check or explicit reviewed
  exception before deactivation. Current item/warehouse deactivation remains
  allowed even with stock. Manual stock writes then reject the inactive record,
  so a resolution/reactivation policy is needed before imposing restrictions.
- New transactions: retain the existing transaction-local active item/warehouse
  checks for manual stock. Decide separately whether outstanding approved POs may
  receive an item deactivated after ordering. Goods Receiving currently validates
  the warehouse as active, but does not add a new inactive-item restriction here;
  its deactivation concurrency policy also remains outside this change.

## Verification

188 Python tests and 11 JavaScript tests pass. Disposable MySQL master-data,
Inventory stock, Procurement, receiving, security and audit suites pass. New tests
verify actual schema limits, boundary/duplicate/malformed inputs, inactive retention,
assignment/deactivation serialization, rollback, CRUD/status preservation, unchanged
stock/history, CSRF rejection and revoked permissions. Compilation, dependencies
and diff checks pass. Tested on disposable MySQL 8.0.46/InnoDB, never company data.

Run the new suite with:

    .venv/Scripts/python.exe -u tests/mysql_inventory_master_smoke.py

Existing stock UUID and Procurement source files are unchanged. All writes in
integration tests use verified fresh temporary servers and synthetic records.
No development/production schemas or records are read or modified.

## Remaining checks and limits

No browser automation was run for Step 3. Manually check create/edit error messages,
retained form values, duplicate errors, category option visibility, Decimal reorder
levels and permission-controlled actions on a synthetic test instance.

Actual company schema drift is not checked. Concurrent master edits are serialized,
but stale browser forms can still overwrite a newer edit; there is no optimistic
version check. Unit/deactivation policies above remain unresolved, and no Inventory
Audit Logs feature is added. Existing metadata labels remain live joins in history.
