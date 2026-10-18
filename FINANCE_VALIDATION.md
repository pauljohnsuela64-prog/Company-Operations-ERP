# Finance Step 2: monetary validation and budget data integrity

Starting state: clean `fix/finance-budget-atomicity` at `43488e0`
(`Fix concurrent finance budget payment validation`). No commits, pushes, branch
switches, company data changes or company migrations were performed in this step.

## Input contract and database compatibility

`finance_validation.py` centralizes pure input validation and transactional
reference checks. Expense and budget create/update repositories validate scalar
input before opening their connection. Finance forms call those repositories and
render clear ValueError messages. Browser monetary maxima match the server, but
backend checks remain authoritative. No GUI layout changes were made.

| Field | Actual schema | Accepted input |
| --- | --- | --- |
| Expense amount | DECIMAL(12,2), CHECK > 0 | 0.01 through 9999999999.99 |
| Budget amount | DECIMAL(14,2), CHECK > 0 | 0.01 through 999999999999.99 |
| Expense date | DATE NOT NULL | Real ISO YYYY-MM-DD dates, years 1000-9999 |
| Budget year | Signed INT NOT NULL | Four-digit calendar years 1000-9999, matching possible expense dates |
| IDs | Signed INT foreign keys | Positive integers through 2147483647; optional references may be blank |
| Description / notes | VARCHAR(255) | Required nonblank expense description; optional notes; at most 255 characters |
| Expense reference | VARCHAR(100) | Optional, at most 100 characters |
| Payment method | Existing ENUM | Blank, CASH, BANK_TRANSFER, CHECK, CARD, OTHER |
| Category code/name/description | VARCHAR(30/100/255) | Existing required fields and limits also enforced by category repositories |

Money is parsed as Decimal, never float. NaN, sNaN, infinities, negatives, zero,
oversized numbers, more than two decimal places (including trailing extra zeros),
exponent notation and malformed separators are rejected. Correctly grouped comma
input remains accepted. Values are not quantized, rounded, truncated or clipped.
The existing browser year selector range 2000-2100 is retained; the backend bounds
are calendar/schema compatibility limits, not a new fiscal scheduling policy.

## References and transactions

Expense writes recheck active category/department/supplier and non-cancelled PO
inside the same transaction as the write, under FOR SHARE locks. This preserves
the existing route rules while closing the lookup/write race and enforcing them
for direct repository callers. Optional blank department/supplier/PO stays NULL.
The existing rules do not require the chosen supplier to match the PO supplier;
this step does not introduce such a financial restriction.

Expense update retains its expense-row FOR UPDATE and DRAFT-only requirement.
Reference lock order is PO -> category -> department -> supplier, after the
expense lock for edits. PO precedes procurement masters. Status/deactivation or
deletion of those references waits until the transaction ends, or wins first and
is observed by the validating writer. Historical links are not rewritten.

Budget creation now explicitly starts a transaction and checks department
existence under a shared lock before insertion. Budget editing retains its
existing budget-row FOR UPDATE, then validates the department. Budget references
have historically allowed inactive departments; they still do. An inactive
current department remains selectable when editing its existing budget so a
notes/amount edit does not force a department transfer.

The database UNIQUE(department_id, budget_year) is the final duplicate boundary.
Both create and edit translate error 1062 after rollback into a friendly duplicate
message, including competing requests. Budget lock timeouts/deadlocks roll back
and report that Finance data changed concurrently and should be reloaded; they
are not silently retried. No early preflight lookup substitutes for uniqueness.

Scalar validation fails before writes; reference validation fails inside the
transaction and rolls back. Genuine database failures still roll back and
propagate for operational diagnosis. No new Finance business audit integration
was added. Existing payment/approval auditing is unchanged.

## Step 1 preserved

`mark_expense_as_paid` and its route are unchanged from the Step 1 commit.
Payment still locks expense -> applicable budget, reads paid spending under
READ COMMITTED after obtaining that budget lock, and commits once. Budget edits
still serialize with payment on the same budget row. Shared department locks
used by budget/expense validation are compatible with each other; no paid-expense
aggregate row locks or global finance lock are introduced.

Annual budgets, expense-date budget year, paid-only consumption, departmentless
handling and existing workflow states remain unchanged. Approval does not reserve
funds. Paid expenses cannot be edited through the draft-edit repository.

## Policy decisions requiring approval

Recommendation: disallow a budget reduction below its already-paid annual
spending, and disallow moving a department/year budget with historical spending.
If exceptions are needed, prefer an explicit approved adjustment/history process
over silently overwriting the historical allocation. **Not implemented.**

If approved, enforce the comparison after obtaining the budget lock using a fresh
READ COMMITTED aggregate, coordinated with payment's lock order. Avoid locking
individual paid expenses while holding the budget. A broader move/override design
needs its own lock-order and history review.

Also requiring policy decisions: whether inactive departments may receive new
budgets, whether supplier/PO references must agree, whether the browser's year
range should become a server-enforced fiscal limit, and whether departmentless
expenses must be restricted. Current behavior is retained for these questions.

## Tests and results

- Complete Python suite: **216 passed**.
- Complete JavaScript unit suite: **11 passed**.
- Disposable MySQL Finance validation: passed with `sql_mode=''` to prove that
  application validation prevents non-strict coercion/rounding/truncation.
- Real forms: invalid amounts, dates, IDs, references, methods and lengths reject
  without business/audit changes on create and edit; exact schema maxima persist.
- Concurrent duplicate budget creation and colliding edits: one succeeds, one
  rejects; the unique department/year invariant remains intact.
- Failure after a real expense INSERT (during its subsequent number UPDATE):
  complete rollback, no partially created expense.
- Active reference validation, CSRF and committed same-session revocation pass.
- Disposable Step 1 payment suite: passed, including three repetitions with two
  real InnoDB LOCK WAIT payers; only one 60.00 payment can commit against 100.00.
  Budget edits/creation, draft edits, duplicate payment, Decimal boundaries and
  payment rollback/audit isolation tests also pass.
- Disposable Procurement, stock reliability, receiving, session/CSRF security and
  existing business audit suites: passed.
- Python/Jinja compilation, JavaScript syntax, dependency and diff checks: passed.

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
.\.venv\Scripts\python.exe -B tests/mysql_finance_validation_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_finance_payment_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_procurement_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_stock_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_receiving_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_security_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_audit_smoke.py
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Runners verify a new temporary MySQL datadir, use loopback and synthetic records,
disable ERP dotenv loading and shut down their disposable servers. The injected
failure trigger exists only in the disposable validation database. No migration
or new dependency is required; existing InnoDB tables, unique constraints, foreign
keys and DECIMAL definitions remain required. Actual company schema/data was not
queried. Existing malformed/historical data is not repaired automatically; adding
further database checks requires profiling and a separately reviewed migration.

## Remaining risks and manual browser checks

Existing budget edits can still reduce allocations below paid spending or move
historical budgets. Best-effort audit gaps and unknown COMMIT outcomes retain
Step 1's documented limitations. Direct SQL bypasses application validators;
unexpected database outages can still return server errors after rollback.
Stale-edit overwrite detection and stronger fiscal/reference policies remain
separate work. No Finance Audit Logs expansion was implemented in this step.

On a disposable synthetic instance, manually check:

1. Expense/budget add and edit: ordinary amounts, grouped commas, exact maxima;
   invalid/overprecision/overflow amounts and invalid dates/IDs via forged forms.
   Confirm readable errors and usable form controls without layout changes.
2. Duplicate budgets and competing tabs: one valid save; the other gets a duplicate
   or reload message, with no partial write. Check an existing inactive department
   budget can still be edited without forcing a new department.
3. Draft create/edit -> approve -> pay/cancel: verify unchanged workflow and
   messages; submit stale payment forms against a changed budget. No new create/
   edit business audit events are expected yet.
4. Viewer/revoked user cannot modify Finance; invalid/missing CSRF gives 400.
   Inspect desktop/mobile layout and actual native form submission/field retention.

HTTP routes and rendered templates were tested automatically; interactive native
browser clicks and deployment HTTPS were not automated for this step.
