# Inventory Categories management

Based on main 290cf8e. This change adds no migration, production grant, stock or
receiving policy, Payroll/HR Lifecycle behavior, quantity conversion or history
rewrite. Item assignments remain controlled by the existing shared category lock.

## Listing

`/inventory/categories` retains `inventory.view`. Search matches category code/name
only, not descriptions, up to 100 characters. Bound LIKE parameters treat `%`, `_`
and `!` literally; existing DB collation applies. Status is all, active or inactive.
Pages contain 25 (default), 50 or 100 records ordered by category name then numeric
ID. Filtered count and rows use one read-only REPEATABLE READ snapshot. Beyond-last
pages clamp. Links preserve search/status/page size; Apply resets the page. Empty
successful results show zero matches. Invalid, duplicate and unknown filters return
400 without silently broadening results. DB read failures return generic 503 and
hide unavailable counts. Existing unbounded all-category and active-category
selector interfaces/SQL remain intact for Item forms and integrations.

## Forms, transactions and audits

Create/edit retain `inventory.categories.manage`, refreshed authentication, CSRF
and schema compatibility admission. Codes remain trimmed/uppercase, names trimmed,
and descriptions optional. Limits remain 30/100/255 characters. Text must be valid
Unicode without controls; descriptions allow tab/CR/LF. Duplicate form fields are
rejected. Existing Jinja-escaped raw form values are retained on validation,
duplicate and unconfirmed write failures. Database UNIQUE constraints remain the
authority for both category code and name, including concurrent submissions.

Create returns its numeric identity only after confirmed commit. Edit locks the
category row and compares normalized values. Missing records fail explicitly;
no-op edits return False without UPDATE, timestamp change or audit; changed edits
return True after commit (formerly None). The category form is the only production
consumer of this result. Status writes lock the category row and distinguish
missing, unchanged and changed records. Explicit `is_active=0/1` form targets make
repeated identical submissions no-ops. Legacy no-target POST callers retain toggle
behavior for compatibility, with its existing retry ambiguity. Invalid/duplicate
status targets fail before a write. Lock conflicts provide reload feedback;
unconfirmed database writes return generic 503 and require reconciliation before
retrying. There is no automatic uncertain-write replay.

CREATE/UPDATE/ACTIVATE/DEACTIVATE use the existing central best-effort audit helper
only after a confirmed changed commit. Failed/no-op writes emit no success event.
Descriptions contain category code/numeric identity, without names/descriptions.
An audit failure cannot reverse the category commit; logs alone are not proof of
business state.

## Item assignments and preserved behavior

Deactivation changes only the category status. It does not detach, reassign,
deactivate or rewrite any Item, stock balance or movement. Existing inactive
category assignments remain eligible for retention while editing that same Item;
new assignments to inactive/nonexistent categories remain rejected. No category
status restriction is added to manual stock, receiving, or Procurement operations
for existing Items. Item activation and warehouse eligibility rules remain intact.

Item assignment acquires category FOR SHARE; category edits/status use FOR UPDATE.
If an assignment commits first, deactivation waits and preserves that assignment.
If deactivation commits first, a waiting new assignment is rejected. Existing Item
then Category lock order remains unchanged; lock conflicts roll back rather than
introduce partial changes. Renaming categories retains the existing behavior of
showing current master labels in joined displays, without rewriting transactions.

## Limitations

Stale forms may overwrite newer edits; no revision migration is added. Opposite
status targets can supersede one another; legacy toggles are ambiguous on retries.
Offset pages may shift between requests during writes. Auditing is best effort,
without durable/exactly-once delivery. Lost commit acknowledgments require record
reconciliation even after a rollback attempt. Leading-wildcard search, full counts
and production category volume remain unqualified for performance. Direct SQL or
legacy writers can bypass application conventions. There are no new unresolved
business-policy restrictions introduced by this feature.

## Verification

`tests/test_inventory_categories.py` uses real Flask rendering/security with company
DB access blocked. `tests/mysql_inventory_categories_smoke.py` uses the verified
fresh disposable MySQL harness and synthetic fixtures: 1,005 rows, 25/50/100 pages,
combined/literal/invalid filters, snapshot counts during a concurrent insert,
code/name duplicates, observed edit/status/assignment lock waits, no-op writes,
rollback, lost acknowledgment and audit SQL failure isolation. Inventory master,
Items, stock, receiving, Procurement, reporting, Warehouse, Finance payment and
schema compatibility suites cover existing integrations. Category Chrome checks
use the existing isolated security runner, verify exact four audit actions,
historical fixtures/assignments, retained escaped forms and viewer/CSRF denial.
No company configuration/database is used. Existing CI discovers the new smoke
suite automatically; native Chrome remains a local check. Tests do not authorize
production deployment or company database operations.
