# Supplier management

Based on main d9f2e8d. No migration, production grant, Payroll/HR Lifecycle change,
financial formula, expense workflow or historical transaction rewrite is added.

## Listing and selectors

`/procurement/suppliers` retains `procurement.view`. Search matches supplier code
and name only, not contact details/addresses. It accepts up to 100 valid Unicode
characters and treats `%`, `_` and `!` literally through bound parameters. Existing
DB collation applies. Status is all, active or inactive. Pages contain 25 (default),
50 or 100 rows, ordered by supplier name then numeric ID; duplicate supplier names
remain allowed. Filtered count and rows share a read-only REPEATABLE READ snapshot.
Beyond-last pages clamp; empty results show zero matches. Apply resets the page;
links preserve search/status/page size. Invalid, duplicate and unknown query keys
return 400 without silently broadening results. Read failures return generic 503
and hide unavailable counts.

Existing unbounded all-supplier and active-supplier selector SQL/interfaces remain
unchanged for Finance and Procurement. `get_supplier_by_id` retains its permissive
missing-ID lookup contract, including zero/negative/unknown numeric IDs, so the
existing PO form can produce its existing validation feedback. Write identities
are validated before a connection is opened.

## Required-field policy and validation

Supplier code and name are required. Contact person, email, phone and address stay
optional on both backend and existing Add/Edit forms. There is no new email/phone
format, contact requirement or address requirement. Column limits remain code 30,
name 150, contact 100, email 150, phone 30, address 255. Text must be valid Unicode
without control characters; address permits tab/CR/LF. Code is trimmed/uppercase,
other fields trimmed, optional blanks stored as NULL: the existing web form
normalization now also runs at the repository boundary. Duplicate form fields are
rejected and existing database uniqueness remains the supplier-code authority.
Names do not become unique. Existing Jinja-escaped raw values remain visible on
validation, duplicate and unconfirmed write errors.

Assignment 2 resolves the frontend/backend mismatch by rendering optional Email
as a text input on Add/Edit. The established backend contract validates type,
length, Unicode and controls, without imposing email syntax. Existing nonempty
legacy contact text can therefore be retained and submitted through native forms.
The 150-character limit, escaping, field name and requiredness are unchanged.
Regression tests cover legacy values, validation redisplay, native browser
submission and optional blanks; no stricter contact/email policy is introduced.

## Transactions, status and audits

Create returns its ID only after confirmed commit. Edit locks the supplier row,
compares normalized values and distinguishes missing, unchanged and changed rows.
No-ops return False without UPDATE/timestamp change/audit; changes return True
only after commit (formerly None). Status now locks the supplier row and returns
False for the existing target, True after a changed commit, and 404 for missing
records (formerly no explicit result). All production callers were reviewed.
Rendered forms use explicit `is_active=0/1` targets: repeats cannot toggle back.
Legacy no-target POSTs keep toggle behavior, with its retry ambiguity. Invalid or
duplicate targets fail before mutation. Lock conflicts provide reload feedback;
DB failures return generic 503 and reconciliation guidance. SQL/commit exceptions
roll back where possible; a lost commit acknowledgment is not proof of rollback.

CREATE/UPDATE/ACTIVATE/DEACTIVATE invoke the central best-effort audit helper after
confirmed changed writes. Failed/no-op writes emit no success event. Audit identity
contains supplier code/numeric ID only; names/contact/email/phone/address are
excluded. Audit failure cannot undo a confirmed supplier commit. Authentication,
`procurement.suppliers.manage`, CSRF, refreshed authorization and schema admission
remain authoritative.

## Relationships and concurrency limits

Deactivation updates only the supplier. Existing PO, expense, paid-history, stock,
movement and receiving records remain intact; no holding/open-order restriction
is added. Finance already obtains a supplier FOR SHARE while validating expense
references, so supplier changes serialize with that boundary. When a valid expense
commits first, later deactivation preserves its reference. When deactivation
commits first, a waiting new expense reference remains rejected as inactive. The
existing active-only Finance edit/reference rules are unchanged.

PO creation retains its route-level active-supplier check for early feedback.
The repository validates a positive signed-INT supplier ID before connecting, then
checks existence/active status with a current `FOR SHARE` read inside the PO
transaction, after locking the approved PR and checking for an existing active PO.
The supplier lock is held through commit/rollback and serializes with status writes.
Deactivation committed first causes creation to reject; PO validation first permits
that valid PO to commit before deactivation proceeds. Parent-before-supplier order
matches Procurement/Finance reference locking; status writes acquire no PR/PO locks.
Existing orders/receiving remain usable
under their existing rules after supplier deactivation. Renaming a supplier still
changes current master labels shown in joined historical views without converting
amounts or rewriting transactions.

Other limitations: stale forms may overwrite newer edits; opposite status targets
can supersede each other; offset pages can shift between requests; audit delivery
is best effort without durable/exactly-once guarantees; uncertain commits require
reconciliation before retrying; production performance of wildcard search/full
counts remains unverified. Direct SQL/legacy writers may bypass these conventions.

## Verification

`tests/test_supplier_management.py` blocks company DB access and verifies policy,
validation, snapshot query binding, no-op/missing writes, retained escaped forms
and security. `tests/mysql_supplier_management_smoke.py` uses the existing verified
fresh disposable MySQL harness: 1,005 tied-name suppliers, 25/50/100 traversal,
concurrent count snapshots, unique-code and edit/status lock waits, rollback,
lost commit acknowledgment, audit failure isolation, real Finance lock orders,
historical references and PO invalid/inactive supplier feedback. The Chrome
workflow verifies pages/forms/status replay/viewer/CSRF, four audit actions,
unchanged historical fixtures/POs and native optional-field submission.

Full Python/navigation/syntax/dependency checks and applicable Procurement,
Finance validation/audit/reporting/payment, receiving and schema compatibility
suites provide regressions. Fixture schemas/permissions exist only on disposable
servers with verified datadirs and synthetic records. No company configuration or
database is used. The smoke suite is discovered by existing CI; Chrome remains
local-only. These checks do not authorize company deployment or database actions.

## Atomic PO supplier eligibility regression

`tests/test_po_supplier_eligibility.py` verifies malformed IDs fail before a
connection, parent/duplicate guards remain first, and missing/inactive suppliers
roll back without inserts. `tests/mysql_po_supplier_eligibility_smoke.py` uses the
verified disposable harness and actual repositories, observing InnoDB lock waits
for both status/creation orderings and duplicate PO conversion. It also checks
missing/invalid/inactive IDs, late SQL and precommit rollback, empty-request
rollback, numbering/copied lines, receiving after deactivation and preserved paid
expense/stock/movement history. CI discovers the new smoke suite automatically.
Routes/forms and postcommit audit calls are unchanged; existing Procurement,
receiving, Supplier and Finance suites provide those regressions. No new Chrome
check is needed for this repository-only behavior. External writers can still
bypass these locks; deadlocks/timeouts involving other writers remain possible,
and a lost commit acknowledgment still requires reconciliation before retrying.
