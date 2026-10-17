# Inventory Step 5: reporting and reconciliation

Started with a clean feature/inventory-improvements checkout at e7f7df7. No business
write paths, schemas, permissions, or pending business policies are changed.

## Stock balances

Stored item/warehouse balances remain separate, including historical inactive
records. Active items with neither a balance nor movement history receive one
virtual zero row labelled "No warehouse balance recorded". No stock row is inserted
and no warehouse association is invented. Items with movement history but no stored
balance are not represented as invented zero stock: inspect them in reconciliation.
Existing warehouse rows and low/out-of-stock indicators remain intact.

## Movement history

GET /inventory/stock/movements supports item, warehouse, movement type, inclusive
from/to dates and search. Search uses existing item/warehouse codes/names, notes,
actor username, reference type/ID and supported receipt number. Percent, underscore
and escape characters are treated literally; parameters are bound. Dates refer to
the database's recorded time without assuming a deployed timezone configuration.

Reports default to 50 rows, allow 1-100 rows per page, and reject malformed filters.
Out-of-range positive pages clamp to the last available page. Filters persist in
previous/next links and applying filters resets the page. Chronological order is
created_at DESC then movement_id DESC, including timestamp ties. Count and rows
use one read-only repeatable-read snapshot; separate page requests may naturally
shift when new movements arrive.

Existing indexes support item/warehouse/date filtering. Leading-wildcard search,
exact counts, deep OFFSET pages and all-history reconciliation can still scan many
rows. Production-sized performance is not certified; query plans and candidate
composite indexes/keyset pagination can be evaluated later without changing schemas
in this task. Filter selectors currently load the existing master lists.

Goods Receipt reference links require procurement.view and an existing source
matching the movement warehouse and item. Missing/inconsistent historical references
are displayed without a link. Manual/other references remain plain recorded values;
no delivery identifiers are invented. Receipt numbers are readable movement source
identifiers; other Procurement source data is not rendered in the history table.

## Reconciliation feasibility

GET /inventory/stock/reconciliation, gated by inventory.view, compares stored
balances to all recorded movements for each pair found in either table. IN and
ADJUSTMENT_IN add; OUT and ADJUSTMENT_OUT subtract. There is no date filter because
a selected date window cannot establish the current balance. Calculations retain
Decimal precision. Pagination and item/warehouse filters are supported.

Current schema has no verified opening-balance amount, coverage-start marker or
history-completeness certificate. Therefore this is an arithmetic comparison,
not a certified physical-stock reconciliation:

- A match is explicitly coverage-unverified, not proof of complete/correct history.
- A numeric difference requires investigation; an unrecorded opening balance or
  missing historical movements can explain it. It is not labelled a confirmed error.
- No movements means opening balance unknown; no computed discrepancy is asserted.
- Movements without a stock row are identified as missing balance records.
- Unsupported/invalid history or invalid stored balances are flagged for review;
  no trustworthy difference is manufactured for those cases.

Only known signed movement types participate in meaningful comparisons. Legacy
adjustments are read, not created. No stock correction, reversal, backfill, opening
balance assumption or historical rewrite is performed. Approval and evidence for
opening/coverage policy are needed before certifying discrepancies as true errors.

## Verification and manual checks

200 Python tests and 11 JavaScript tests pass. Disposable MySQL reporting, Inventory
stock, master-data, Procurement, receiving, security and audit suites pass. New tests
cover zero rows/no writes, warehouses, literal search, combined filters/date edges,
pagination/ties, source links and permission changes, signed adjustments, missing
history/balances, coverage warnings and read-only business/audit snapshots. Tests
use verified temporary MySQL 8.0.46 servers and synthetic records only. Compilation,
dependency and diff checks pass. No development/production database is accessed or
migrated. No new dependency or schema change is required.

Run the new suite:

    .venv/Scripts/python.exe -u tests/mysql_inventory_reporting_smoke.py

Browser automation was not run for Step 5. On an isolated synthetic instance,
manually verify desktop/mobile filter usability, pagination preserving filters,
zero-row warehouse labels and low-stock badges, dates in the deployment timezone,
long notes, permitted/denied receipt links, and clear reconciliation warnings.
Do not adjust balances based solely on this report.
