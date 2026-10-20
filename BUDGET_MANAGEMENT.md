# Department Budget management

This feature changes Budget management only. It adds no schema migrations, grants,
financial policy, Payroll/lifecycle functionality or production actions. Updated
main includes the approved Warehouse PR #15 (`0a33933`); the Budget feature is based
on that merge, rather than duplicating Warehouse work from the older checkpoint.

## Listing contract

`/finance/budgets` retains `finance.view` and defaults to the current calendar year.
Accepted query keys are `year`, `department_id`, `search`, `page` and `page_size`.
Year is 1000-9999. Omitted Department means all; a positive existing/nonexisting ID
is an exact filter. The legacy `none` option still returns zero, since budgets
require Departments. Valid unknown IDs stay selected instead of reverting to All.
Search matches Department code/name only, not sensitive notes or amounts, and is
bounded to 100 Unicode characters. `%`, `_` and `!` are literal search characters;
values and pagination use bound parameters. Existing DB collation applies.

Page sizes are 25 (default), 50 and 100. Page is a positive ASCII integer through
2147483647; beyond-last pages clamp. Order is year DESC, Department name ASC,
Budget ID ASC. Links preserve year/Department/search/page size. Filter submission
resets the page. Inactive and historical Departments/budgets remain discoverable.
Malformed, duplicate and unknown filters return 400 without broader substitute
results. This intentionally replaces the old invalid-year redirect/fallback.
No automatic fallback to the current year occurs for an invalid submitted year.
Read failures return generic 503, with unavailable totals hidden instead of fake
zeroes. Empty successful results are distinct from failed loads.

The original list SELECT is shared verbatim as `BUDGET_LIST_BASE`. It still sums
PAID expenses by Department and YEAR(expense_date), treats absent spending as zero,
and computes remaining as budget minus paid spending. Full filtered count and
sums are calculated from that same SELECT in one InnoDB READ ONLY REPEATABLE READ
snapshot with the page rows. Cards represent ALL matches, not just displayed rows.
Budgetless/departmentless expenses stay excluded. Existing usage percentages,
progress widths, exact exhaustion/over-budget labels and rounding stay unchanged.

Legacy `get_all_department_budgets(year=None)` stays unbounded with the original
optional-year contract and query. `get_budget_summary`, budget details/paid expense
queries, payment advisory checks, expense payment/approval logic and reports are
unchanged. The new page API is separate from those consumers.

The central schema manifest does not include Finance engines. The management
repository therefore checks Budget storage is InnoDB before writes, and both
Budget/Expense storage before paged reads, using read-only metadata queries on
the same connection. Missing/nontransactional tables fail with 503; no conversion,
migration, grants or automatic repair occur. Legacy report helpers are unchanged;
this local check does not claim to harden every unrelated Finance entry point.
DDL/storage changes still require a controlled maintenance window; metadata
checks do not fence concurrent external DDL.

## Forms and write boundaries

Create/Edit keep `finance.expenses.manage`, authentication refresh, CSRF and schema
admission. Raw Department/year/amount/notes values are retained and Jinja-escaped
on errors. Unlisted submitted Departments remain visible with a neutral label.
Text inputs preserve malformed years/amounts instead of browser number controls
silently blanking them; numeric/decimal input modes remain. The server owns exact
validation. Existing positive Decimal(14,2) bounds, grouped decimal input and
1000-9999 year rules remain. Notes stay optional, at most 255 characters; invalid
Unicode and controls other than tab/CR/LF are rejected. Duplicate form fields are
rejected, and unique Department/year keys remain the concurrency authority.

Existing Department eligibility is preserved: the repository accepts any existing
Department, including inactive ones (`lock_department` without active=True).
Create GET still shows the existing active choices; Edit retains its current
inactive Department. This feature adds no active-only repository restriction.
Missing edit records produce explicit feedback. Existing input/duplicate feedback
keeps its 200 form-response contract; duplicate form fields return 400, a record
lost after lookup returns 404, and unconfirmed SQL/commit writes return generic 503
with a refresh/reconciliation instruction. Never assume an unconfirmed commit
rolled back, and do not automatically replay it.

Create still returns its numeric ID only after commit. Edit preserves the existing
Budget FOR UPDATE then Department FOR SHARE lock order. Identical values are now
a no-op (False, no UPDATE/timestamp change/audit); changed commits return True
(previously None). Production callers were reviewed; the Budget form consumes
that result. Existing budget/payment serialization, unique-key/deadlock feedback,
Department existence checks and rollback behavior remain. There is no new rule
preventing a budget reduction below already-paid expenses or a Department/year
key move. Those existing behaviors remain subject to separate financial policy.

## Auditing and limitations

Confirmed changes use the existing central best-effort helper for Budget CREATE
and UPDATE, preserving numeric Budget identity, Department identity/code and year.
Amounts and notes are excluded. Failed/no-op writes emit no success event. Audit
failure cannot reverse a confirmed Budget commit. Audit delivery has no durability,
exactly-once or tamper-proof guarantee. An uncertain committed write can lack an
audit; operators must reconcile rather than infer financial state from logs alone.

Stale forms can still overwrite newer edits; no revision migration is introduced.
Snapshots are per response, so offset pages can shift during concurrent writes.
Full filtered sums/counts, leading-wildcard searches and large Department option
sets require production performance qualification. No index migration is added.
Direct SQL/legacy writers can bypass application conventions. Local/CI tests do
not approve production deployment or company database operations.

## Verification

Commands and coverage are in [tests/README.md](tests/README.md). Unit fixtures
forbid company DB access; native SQL and Chrome use only the existing verified
disposable MySQL launcher with synthetic records. Chrome remains a local workflow.
