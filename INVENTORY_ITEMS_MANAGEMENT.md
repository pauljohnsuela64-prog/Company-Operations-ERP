# Inventory Items management

Based on main bb34f36. No migrations, production grants, stock/receiving policy,
Payroll, HR Lifecycle, or financial formulas are changed.

## Listing

`/inventory/items` retains `inventory.view`. Search matches item code/name only,
up to 100 characters, using bound parameters with literal `%`, `_` and `!`.
Category accepts all (blank), no category (`none`), or an exact positive ID.
Inactive categories and their existing items remain discoverable; unknown IDs
remain selected and return no matches. Status is all, active or inactive.

Pages contain 25 (default), 50 or 100 rows, ordered by item name then numeric ID.
Count and page rows share a read-only REPEATABLE READ snapshot. Beyond-last page
requests clamp; empty results show zero matching items. Filter submission resets
the page and links preserve all filters. Malformed, duplicate and unknown query
keys return 400 without silently broadening results. Database read failures return
503 with unavailable counts hidden. Existing unbounded `get_all_inventory_items()`
and active selector contracts used by stock and Procurement remain unchanged;
the duplicate active selector definition is consolidated.

## Writes and security

Create/edit retain `inventory.items.manage`, authentication refresh, CSRF and schema
admission. Validation follows existing text lengths and Decimal(12,2) reorder
bounds (zero allowed). Codes remain normalized to uppercase. Item text rejects
invalid Unicode/control characters; descriptions permit tab/CR/LF. No shared
category/warehouse validation policy is changed. Duplicate form fields are rejected.
Raw form data is escaped and retained, including unknown categories/custom units
and malformed reorder values. Database uniqueness remains the item-code authority.
Existing inactive category assignments may be retained, but new inactive category
assignments remain forbidden. Disappearing edit/status records fail explicitly.

Updates lock the item row before the category eligibility lock, preserving the
existing order. Equivalent normalized edits return False with no UPDATE, timestamp
change or audit. Changed updates return True only after commit (formerly None).
Production callers were reviewed; only the Item edit form consumes this result.
Status writes lock the item row and distinguish missing, unchanged and changed
records. This serializes with existing manual stock/Procurement item eligibility locks.
No stock or movement records are rewritten and holding stock does not prevent
deactivation. Receiving from an already sent PO retains its existing ability to
receive an inactive item; it does not introduce an active-item eligibility rule.
Warehouse eligibility and goods-receiving behavior remain unchanged.

Rendered status forms send an explicit active/inactive target. Replaying the same
target produces a no-op rather than reversing it. Legacy POST callers without a
target retain toggle behavior and its retry ambiguity; integrations should submit
`is_active=0` or `1`. Duplicate/invalid status targets fail before the write.

CREATE/UPDATE/ACTIVATE/DEACTIVATE use the central audit helper only after confirmed
changed commits. Descriptions include item code/numeric identity, not names,
descriptions, quantities or units. Failed/no-op writes emit no success event.
Audit failure cannot undo a confirmed Item commit. Duplicate codes and lock
conflicts return safe feedback; database write errors instruct reconciliation
before retrying, without exposing SQL or automatically replaying uncertain writes.

## Policy questions and limitations

Existing code permits changing item code/name/category/unit/reorder level after
stock movements exist. These edits remain allowed. Historical reports join the
current item record and therefore show the current unit label; changing `pcs` to
`box` does not convert any stored quantities. Whether to prohibit such edits,
version units, or add conversions is a business-policy/schema decision outside
this change. No new restriction or historical data conversion is introduced.

There is no revision check: stale edits can overwrite newer edits and opposite
status targets may supersede one another. Offset pages may shift between requests
under concurrent writes. Auditing is best effort, without durable/exactly-once
delivery. Lost commit acknowledgments require reconciliation, even after a rollback
attempt. Leading-wildcard search, full counts and large category lists need
production performance qualification. Existing schema admission requires InnoDB;
direct SQL/legacy writers can bypass application conventions.

## Verification

Run `python -B -m unittest discover -s tests -q`,
`python -B tests/mysql_inventory_items_smoke.py` and
`python -B tests/mysql_inventory_items_browser.py` with the existing local binaries.
Unit fixtures block company DB access. The SQL/Chrome harness starts a new MySQL
server with `--no-defaults`, verifies its temporary datadir, and uses synthetic
records only. Test permissions exist only on that disposable server. Existing
Inventory master, stock, receiving, Procurement, inventory reporting, Warehouse,
Finance payment and schema compatibility suites provide integration regressions.
The new smoke suite is discovered by existing CI; Chrome remains a local check.
These checks do not authorize deployment or company database operations.
