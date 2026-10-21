# Finance Expense Categories management

Based on latest origin/main 3ef98293d7a2a6f4c706993162da7cbf53d4f476 (Supplier
PR #19 merge), which contains the supplied d9f2e8d checkpoint. No financial formula,
approval/payment workflow, migration, production grant, Payroll or HR Lifecycle
behavior is changed.

## Listing

`/finance/expense-categories` retains `finance.view`. Search matches category code
and name only, not descriptions, up to 100 valid Unicode characters. Bound LIKE
parameters treat `%`, `_` and `!` literally; existing DB collation applies. Status
is all, active or inactive. Pages contain 25 (default), 50 or 100 rows ordered by
category name then numeric ID. Duplicate category names remain allowed. Filtered
counts and rows share a read-only REPEATABLE READ snapshot. Beyond-last pages
clamp, Apply resets the page and navigation preserves filters. Invalid, duplicate
and unknown filters return 400 without broader substitute results. Empty results
show zero matches; failed loads return generic 503 and hide unavailable counts.

The unbounded all-category, active-category and by-ID selector SQL/interfaces used
by expense forms and reports remain unchanged. By-ID lookup keeps its existing
missing/invalid numeric identifier behavior. The separate page helper does not
paginate or filter those legacy consumers.

## Validation, writes and auditing

Create/edit retain `finance.categories.manage`, authentication refresh, CSRF and
schema admission. Code/name remain required, description optional; lengths stay
30/100/255. Category text must be valid Unicode without controls; descriptions
permit tab/CR/LF. Web forms retain trimmed uppercase codes; direct repository calls
retain their original code casing and trimming behavior. Duplicate form fields
are rejected; database uniqueness remains the code authority. Names do not become
unique. Raw form values are retained and Jinja-escaped on errors. Read-only viewers
no longer see management status forms; POST permission checks remain authoritative.

Create returns the numeric ID after confirmed commit. Edit/status lock the category
row and distinguish missing, unchanged and changed records. Boolean changed/no-op
return contracts remain True/False. Missing records now raise an explicit 404
validation error rather than conflating disappearance with a no-op; production
write consumers are the management routes and were reviewed. Unchanged edits and
status targets perform no UPDATE, timestamp change or audit. Rendered status forms
send `is_active=0/1`; repeated targets cannot toggle the record back. Legacy
no-target callers retain toggle behavior. Invalid/duplicate targets fail before
mutation. Deadlock/lock-wait errors roll back and give reload guidance; unconfirmed
writes return generic 503 with reconciliation instructions, without SQL leakage or
automatic replay.

CREATE/UPDATE/ACTIVATE/DEACTIVATE invoke the central audit helper only after a
confirmed changed commit. Identity contains numeric category ID/code, not names,
descriptions or financial amounts. Failed/no-op writes create no success event.
Audit failure cannot reverse a confirmed category commit.

## Storage and expense references

The existing global engine manifest does not cover Finance tables. Management
writes and the new page API therefore verify `expense_categories` is InnoDB through
read-only metadata on the same connection, failing closed with 503 on unsupported
storage. No conversion, DDL, migration or permission repair occurs. Legacy readers
retain their contracts; this local check does not claim to harden every Finance
entry point or fence concurrent external DDL. Storage maintenance requires a
separate controlled operation.

The existing expense reference validator takes category FOR SHARE; management
updates/status use FOR UPDATE. If an expense reference commits first, deactivation
waits and preserves it. If deactivation commits first, a blocked new reference is
rejected. Existing expense write eligibility remains active-only, including an
edit that retains an existing inactive category. No historical reassignment,
conversion, status update, expense amount change or delete occurs when a category
is deactivated. Historical DRAFT/APPROVED/PAID/CANCELLED records and reports remain
available under their existing rules. Renames continue to change current category
labels in joined views without rewriting old transactions. No new business-policy
restriction is introduced.

## Limitations

Stale edits may overwrite newer values; no revision migration is added. Opposite
status targets can supersede one another; legacy toggle retries are ambiguous.
Offset pages can shift between requests during concurrent writes. Auditing remains
best effort without durable/exactly-once delivery. Uncertain commits require
reconciliation even after attempted rollback. Wildcard searches/full counts need
production performance qualification. Direct SQL/legacy writers can bypass
application conventions. No unresolved new financial-policy decision is introduced.

## Verification

`tests/test_expense_category_management.py` blocks company DB access and verifies
filters, binding/counts, legacy casing/lookup contracts, storage checks, no-ops,
retained escaped forms, permissions/CSRF and schema admission.
`tests/mysql_expense_category_management_smoke.py` uses the existing verified fresh
MySQL harness: 1,005 tied-name rows, 25/50/100 traversal, concurrent snapshot counts,
observed duplicate/edit/status/expense lock waits, SQL/commit rollback, lost commit
acknowledgment, audit failure isolation, category assignment/amount preservation,
active-only reference rules and actual MyISAM rejection without repair. Chrome
checks native forms, pages, status replay, four exact audit actions, unchanged
historical fixtures/expenses and viewer/CSRF denial. Existing Finance validation,
audit, reporting, payment, Budget and schema suites supply regressions. Existing
Finance audit missing-status coverage now expects explicit 404 and still asserts
zero success audits. Fixture schemas/permissions exist only in disposable verified
datadirs, never company databases. CI discovers the new SQL smoke automatically;
Chrome remains local-only. Verification does not approve production deployment.
