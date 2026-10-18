# Finance Step 3: central business-action audit logs

Started from clean `fix/finance-budget-atomicity` at `69ddf1c`
(`Improve finance monetary validation and data integrity`). No commits, pushes,
merges, branch changes, actual company data changes or company migrations were
performed. Business repositories and financial policies are unchanged.

## Events

All events use the existing `record_audit_event` helper, acting session user ID /
fresh username and module FINANCE. New events store the numeric primary key in
the existing VARCHAR entity_id column (the audit writer serializes IDs as text).
Readable labels and the numeric ID also appear in concise descriptions.

| Entity type | New actions | Readable information |
| --- | --- | --- |
| EXPENSE | CREATE, UPDATE, CANCEL | Generated expense number |
| EXPENSE_CATEGORY | CREATE, UPDATE, ACTIVATE, DEACTIVATE | Category code |
| DEPARTMENT_BUDGET | CREATE, UPDATE | Department ID/code and applicable budget year |

Descriptions omit amount, budget amount, payment/reference details, notes,
category/department names, free-text descriptions, credentials and secrets.
Budget identity/year come from the validated successful submission, including a
changed department/year. It is not inferred by re-reading a potentially edited
budget afterwards. Existing preloaded department codes are reused; if a department
is not in that list, an optional best-effort lookup supplies its code. Numeric
department/year remain present even when that label lookup fails.

## Existing events and helper compatibility

APPROVE and MARK_PAID keep their existing action names, EXPENSE entity type and
readable expense number in entity_id. Their descriptions now also include the
numeric expense ID, satisfying both identity requirements without changing the
existing search/filter identity convention. There is still exactly one audit
call at each existing action site; no second approval/payment hook was added.

The helper's optional `preserve_entity_id=True` appends a looked-up identifier to
the description instead of replacing the numeric entity_id. It is used by new
Finance lookup-based events. The default remains False, preserving all existing
Procurement, Inventory, HR, Payroll and Administration call behavior. Missing or
failed optional lookups keep the numeric identity; they do not undo the action or
prevent a best-effort audit insert.

No audit schema migration, new role permission, dependency, UI layout or audit
filter changes are needed. Existing audit_logs.view controls the central screen.

## Commit and failure boundaries

- Hooks run only after the business repository returns from its commit.
- CREATE reuses returned IDs / generated expense number. Expense edits reuse the
  stable ID/number loaded by the existing route. Cancellation resolves its label
  inside the audit helper's exception boundary after commit.
- Expense UPDATE/CANCEL false results do not audit. Category UPDATE/status checks
  its existing changed-row result: a stale/missing/no-op write gives a warning
  instead of a success audit. Budget UPDATE preserves the current None-on-success
  API while guarding an explicit False result.
- Validation failures, permission/CSRF denial, failed commits/rollbacks and rejected
  workflow transitions do not reach the success hook.
- Existing cancellation/approval/payment row locks prevent repeated completed
  transitions. Repeated cancellation requests cannot create a second CANCEL.
- Separate successful saves may each produce UPDATE events. This step adds no
  submission-idempotency tokens and does not reinterpret an accepted save as a
  business-policy violation. A category update whose repository reports no
  changed row produces no event.
- Audit storage remains a separate best-effort transaction. Insert/lookup failure
  is logged by the helper and cannot reverse the committed business operation or
  turn its response into an audit error.

The atomic payment repository/READ COMMITTED budget locking and Step 2 Decimal,
date, reference and duplicate-budget validation were not modified. Existing
finance.expenses.manage, finance.categories.manage, finance.expenses.approve,
finance.expenses.pay, fresh per-request authorization and global CSRF remain in
place. Budget reduction/reassignment restrictions were not implemented.

## Tests

`tests/test_finance_audit.py` checks each new action's actor, numeric ID, readable
label, privacy, failed business operations/commit boundaries, unsuccessful
returns, audit failure isolation, CSRF, committed permission revocation, disabled
accounts and lookup failures. It also checks exactly one existing APPROVE /
MARK_PAID call with the retained legacy identity. Company DB access is blocked.

`tests/mysql_finance_audit_smoke.py` uses the existing disposable MySQL launcher:
fresh temporary verified @@datadir, --no-defaults, loopback server, synthetic
records, disabled dotenv and graceful shutdown. It exercises real routes,
repositories, templates and audit SQL, including:

- All nine new event types with persisted actors, IDs, labels and budget years.
- Existing APPROVE/MARK_PAID exactly once, including repeated-transition denial.
- Duplicate/invalid/stale/paid cancellation failures with no success row.
- Real late business write failure after INSERT: full rollback and no audit.
- Real audit INSERT failures for each new business write path using a trigger
  only inside the disposable database: business changes stay committed.
- Two concurrent cancellation submissions: one committed transition/event.
- Forged POST, missing/invalid CSRF and fresh permission revocation with unchanged
  business/audit snapshots.

Results:

- Complete Python suite: **224 passed**; JavaScript unit suite: **11 passed**.
- Disposable Finance audit, atomic payment and validation suites passed.
- Atomic payment regression still observes two real InnoDB LOCK WAIT payers:
  only one of two 60.00 expenses commits against a 100.00 annual budget, with
  exactly one MARK_PAID audit; repeated in three trials.
- Existing disposable business audit, session/security, Procurement, stock and
  receiving compatibility suites passed.
- Python/Jinja compilation, JavaScript syntax, dependency and diff checks passed.

Commands from the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
.\.venv\Scripts\python.exe -B tests/mysql_finance_audit_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_finance_payment_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_finance_validation_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_audit_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_security_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_procurement_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_stock_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_receiving_smoke.py
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

## Remaining risks and policy decisions

Audit is not crash-atomic with business writes: a process crash or audit outage
after commit can leave an unaudited action. There is no retry/outbox or recovery
backfill, and no exactly-once delivery promise across crashes. An uncertain COMMIT
response can similarly leave audit delivery unresolved. Existing records are not
backfilled. Direct repository calls outside the web business-action routes do not
automatically create central audit rows, matching existing ERP architecture.

Display codes can be renamed and optional label resolution can fail. Numeric IDs
and budget department/year are retained as canonical references. The schema keeps
mixed legacy readable IDs / new numeric IDs; no global audit identity migration
was attempted.

Existing budget reductions below paid spending, reassignment of historical budgets,
departmentless expense handling and outstanding approval/ownership policies remain
unchanged and require separate approval if they are to be restricted.

## Manual browser verification (disposable synthetic data only)

1. Create/edit/cancel an expense. In Administration -> Audit Logs, filter FINANCE
   and the relevant action. Confirm one matching event, actor, numeric ID and
   expense number; no amount, reference, notes or free-text description.
2. Create/edit a category and deactivate/reactivate it. Check matching code/ID and
   action. Re-submit an unchanged edit: no false success event if the repository
   reports no changed row. Check the warning remains readable.
3. Create/edit a department budget, including changing its year and editing an
   inactive-department fixture. Verify numeric budget/department IDs, readable
   code and the submitted year, with no budget amount or notes.
4. Approve/pay a separate approved fixture. Confirm exactly one APPROVE and one
   MARK_PAID; repeat each completed transition and cancellation: no extra success
   event. Re-run over-budget/duplicate-budget/overprecision cases: no success log.
5. Use a viewer/revoked synthetic account and forged/missing-token submissions.
   Confirm denial and no business/audit changes. Inspect existing central filters,
   search, desktop/mobile layout and native form interactions.

HTTP routes and real rendered templates were tested automatically. Native browser
clicks and deployment HTTPS were not automated for this step. Await review before
Finance Step 4.
