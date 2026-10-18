# Finance Step 1: atomic annual-budget payment enforcement

## Problem and scope

Previously the payment route called `check_expense_against_budget()` on one
connection, then `mark_expense_as_paid()` on another. Each of two requests could
see the same remaining budget and pass, then both commit PAID. Locking only the
individual expense did not serialize payments for different expenses.

The payment repository now owns the authoritative budget validation and update.
The route retains its `finance.expenses.pay` decorator, global CSRF, fresh
request-local authorization, redirects/flashes, and post-commit audit call.
`check_expense_against_budget()` remains an advisory preview on the detail page;
its result cannot authorize a payment. No UI or other financial policy changed.

## Transaction and locks

Each payment uses one connection and an explicit READ COMMITTED transaction:

1. Lock the expense by primary key using SELECT FOR UPDATE. Read the persisted
   current status, amount, department and expense date; require APPROVED and a
   positive Decimal amount. Submitted form values are not financial inputs.
2. For a linked department, derive the year from that locked expense date. Lock
   the unique `(department_id, budget_year)` budget row using SELECT FOR UPDATE.
   Missing budget means validation failure and rollback.
3. Only after acquiring that lock, read SUM(amount) of PAID expenses for the
   same department/year. This is a nonlocking READ COMMITTED statement, so it sees
   payments committed by previous lock holders, even when this request waited.
   Add the current amount and compare with the locked budget using Decimal.
4. Update the expense to PAID with an additional APPROVED predicate, verify one
   affected row, and commit. Any validation or database failure rolls back.
5. Only then does the route attempt its existing FINANCE/MARK_PAID audit event.
   Rejected/duplicate transactions never reach that success event. Audit storage
   failure remains isolated from the committed business action.

Lock order is expense -> budget. The spending read must remain nonlocking:
locking other expense rows while holding the budget could deadlock against a
second payer holding its own expense and waiting for the budget. READ COMMITTED
is explicit for this transaction only; no server-wide default changes are made.
Unrelated budgets can proceed independently; there is no global finance lock.

## Existing policies preserved

- Budgets are annual and use expense date, not payment date.
- Only PAID expenses consume budget; approved/unpaid amounts are not reserved.
- Linked expenses require an applicable budget.
- Departmentless expenses retain the existing no-budget-control policy.
- Only APPROVED expenses may become PAID. Paid records cannot be edited/cancelled
  through the existing expense repositories.
- No tax, ledger, bank transfer, reservation, payment-processing or payment-method
  rules are introduced.

## Concurrent edits and creation

Budget editing already locks the budget row before updating it. An edit committed
first is observed by the waiting payment; a payment committed first is evaluated
against the budget in force at its serialization point. Moving the budget to
another year while payment waits results in a missing applicable budget and a
rejection. Budget creation's unique index arbitrates an uncommitted matching
insert; payment proceeds only if the committed matching row exists, otherwise
rejects. If creation has not begun when payment sees no budget, payment rejects
and can be retried after budget creation commits.

Expense editing already locks the expense and only permits DRAFT records.
Payment uses the same row lock and reads current data. A payment queued behind a
draft edit rejects the current DRAFT status; an editor queued behind payment
cannot modify its PAID result. Approval also locks the expense. No reliance on a
form preview or an unlocked expense lookup remains.

## Compatibility and deployment

No migration, new permission, dependency or configuration setting is required.
The repository function still returns True on successful commit and raises
ValueError for business validation failures. Existing MySQL errors still propagate
after rollback; they do not produce success messages or success audit events.

Deployment requires the existing foreign keys, the unique department/year budget
constraint, DECIMAL money columns and transactional InnoDB expense/budget tables.
The disposable tests use the checked-in schemas. Actual company schema/engine
state was not queried or changed. Review it through the normal deployment process.
Do not introduce concurrent direct SQL writers that bypass this payment path.

## Verification

Run from the project root using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
.\.venv\Scripts\python.exe -B tests/mysql_finance_payment_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_audit_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_security_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_procurement_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_stock_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_receiving_smoke.py
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

The Finance runner uses the existing launcher: --no-defaults, temporary datadir,
loopback-only MySQL, verified @@datadir, synthetic records, dotenv disabled and
graceful shutdown. No configured company database is accessed or migrated.

The decisive test repeats three times: hold the common budget lock, start two
real route requests on separate connections for approved expenses of 60.00 each
against a 100.00 budget, observe **two LOCK WAIT transactions in InnoDB**, then
release the lock. Exactly one payment commits, the other remains APPROVED with
paid_at NULL, total spending is 60.00, and exactly one success audit persists.

Additional tests cover exact 0.10+0.20=0.30, annual/date boundaries, unpaid amounts
not reserved, missing budget, departmentless payments, duplicate submissions,
different-budget independence, budget edits in both orders, budget key moves,
budget creation commit/rollback, concurrent draft editing, injected failure after
a real UPDATE and before COMMIT, lock release/retry, audit outage isolation,
valid-token forged requests, CSRF rejection and committed permission revocation.
Unit tests verify isolation/lock ordering and rollback boundaries. Existing audit
tests now expect authoritative rejection from the payment repository, not a
separate route-level preflight.

Final results on `fix/finance-budget-atomicity`:

- Complete Python suite: **211 passed**.
- JavaScript unit suite: **11 passed**.
- Disposable MySQL: Finance payment, business audit, session/CSRF security,
  Procurement, stock reliability and receiving suites all passed.
- All application/test Python and Jinja templates compile; dependency check
  reports no broken requirements; git diff whitespace checks pass.
- No company data or schema was accessed/changed, and no migration was run.

## Remaining risks and policy decisions

- Existing budget editing permits lowering a budget below already-paid spending
  or moving a budget away from historical spending. The concurrent-edit test
  deliberately preserves this behavior. Decide separately whether those edits
  should be restricted or require approval; this step changes no edit policy.
- Historical overspending is not repaired. A linked payment exceeding the current
  budget will reject; existing PAID amounts remain recorded.
- Departmentless expenses still bypass budgets. Requiring a department needs an
  approved policy change.
- Success audit is best effort on a separate connection; storage failure/crash can
  leave a committed payment without an audit row. No new guarantee is claimed.
- Connection loss while COMMIT is in flight can leave the client uncertain. The
  status guard prevents a second successful transition on retry, but a lost audit
  is not reconstructed. No automatic retry is introduced.
- Deadlocks/lock timeouts from other writers remain possible. Failed transactions
  roll back; callers can reload and retry. Large paid-expense aggregates may need
  later index/performance work, not a change to financial policy.
- Authorization is refreshed at request start. An already-authorized in-flight
  request may finish after concurrent permission revocation, as before.

## Manual browser acceptance (disposable synthetic data only)

1. As a permitted payer, open an APPROVED linked expense. Pay an amount exactly
   equal to remaining budget; verify success flash, PAID status, paid timestamp
   and one FINANCE/MARK_PAID audit. Reload/resubmit: rejection and no second event.
2. Try a one-cent over-budget payment and a department/year with no budget.
   Verify the peso overage/year/department error, unchanged APPROVED status and
   no success audit. Confirm a departmentless approved fixture follows the
   existing allowed policy.
3. In two sessions, open two 60.00 expenses against a 100.00 budget and submit
   together. One succeeds, the other rejects after waiting; reload both. The
   deterministic simultaneous MySQL test already proves this backend result.
4. Change the budget after opening the detail page, then submit the stale form.
   Verify the committed budget controls the result, not the displayed preview.
5. A viewer without pay permission must not pay using a forged valid-token POST;
   missing/invalid CSRF must give 400. Revoke the synthetic payer's grant: its
   next request must deny. Check navigation/layout remains unchanged.

Native browser clicks and deployment HTTPS were not automated for this Finance
step. No company records, branch changes, commits, pushes or merges were made.
