# ERP testing and continuous integration

## GitHub Actions CI

[ERP CI](../.github/workflows/erp-ci.yml) runs on pull requests targeting `main`,
pushes to `main`, and manual `workflow_dispatch`. Draft pull requests are included.
Manual dispatch becomes available after the workflow exists on the default branch.
The workflow has three independent jobs:

| Job | Runner | Checks |
| --- | --- | --- |
| Python unit tests and syntax | Ubuntu 24.04, Python 3.14 | Install `requirements.txt`; `pip check`; compile tracked Python; parse Jinja templates; complete unittest discovery |
| JavaScript tests and syntax | Ubuntu 24.04, Node 24 | `node --check` for tracked JS/CJS files; navigation tests; no npm install |
| Disposable MySQL integration | Windows 2025, Python 3.14 | Discover compatible `mysqld`; run all `tests/mysql_*_smoke.py` sequentially, currently 32 suites |

Python, Node and runner labels select supported release lines, not immutable OS
images. Official checkout/setup Actions are pinned to full commit SHAs with release
comments. Review upstream releases before updating those pins. The hosted Windows
image currently supplies MySQL 8.0.46, according to the
[official image inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md).
The [official installation script](https://github.com/actions/runner-images/blob/main/images/windows/scripts/build/Install-MysqlCli.ps1)
installs the MySQL MSI under Program Files and adds its bin directory to PATH.
The helper discovers `mysqld` through PATH or the ProgramFiles MySQL installation;
there are no developer-specific absolute paths in the workflow. It checks the
actual executable version and rejects MariaDB/versions below MySQL 8.0.16. Image
changes or a missing/incompatible executable fail the job rather than skip tests.
The first hosted run is still required to establish runner compatibility; a local
pass is not a GitHub Actions result.

### Reading results

Open the pull request's Checks tab or the repository's Actions tab and inspect all
three job results for the current commit. Each named step identifies its check;
MySQL suites have separate log groups. Exceptions, nonzero child exit statuses and
five-minute integration-suite timeouts fail the job. Job limits are 15 minutes
for Python, 10 for JavaScript and 35 for MySQL. A failed integration run stops at
the failing suite; later suites are not claimed as passed. Cancelled, skipped,
missing or pending checks are not passes. New runs cancel superseded runs for the
same ref. Required branch-protection checks need separate repository-owner setup;
this workflow does not change repository settings or merge anything.

### Isolation and security

No workflow job uses company database settings, repository/environment secrets,
production targets or deployment environments. Token permissions are only
`contents: read`, checkout credentials are not persisted, and there are no artifact
uploads or persisted Actions dependency caches. `.env` remains untracked; never add it or credentials
to a commit. A checked-out `.env.example` is configuration documentation, not a
company environment. Unit fixtures block/mock database access and disable dotenv.
Compilation and Jinja parsing do not import the application.

Each MySQL launcher retains its existing `--no-defaults`, fresh temporary datadir,
dynamic loopback port, synthetic fixtures and datadir-verification assertions before
business data creation and shutdown. It does not connect to an installed default
service. Its empty-password root account exists only on the temporary loopback
server; no company credentials or passwords are printed. Schema/migration tests
operate solely on that disposable instance. The dedicated schema-gate suite runs
the real inspector; existing scoped repository fixtures remain unchanged. Mocked
unit coverage is not equivalent to these integration checks. Jobs run on ephemeral
GitHub-hosted VMs, never on a company-connected self-hosted runner.

### Equivalent manual commands

Use a clean Python 3.14 virtual environment and Node 24 from the repository root:

```powershell
python -m pip install -r requirements.txt
python -m pip check
python -B scripts/ci_checks.py python
python -m unittest discover -s tests -q
python -B scripts/ci_checks.py javascript
node --test tests/horizontal_navigation.test.cjs
python -B scripts/ci_checks.py mysql
```

For an explicitly installed local server binary, use
`python -B scripts/ci_checks.py mysql --mysqld "PATH_TO_MYSQLD"`.
This accepts a binary path, never a database address or credentials. MySQL CI uses
Windows to retain the native launchers. Linux/macOS MySQL launchers are not certified
by this workflow. Missing prerequisites are failures. `openpyxl==3.1.5` is included
in requirements because the application and Excel tests import it; an existing
workstation installation is not sufficient for a fresh CI environment.

### Browser and deployment boundaries

Native Chrome workflows remain local-only in this initial CI release. Windows
hosted images include Chrome, but browser startup/cleanup and the existing native
executable assumptions need a separate hosted qualification; historical intermittent
teardown timeouts remain a reason to avoid claiming browser coverage from unit or
MySQL-only jobs. Run the existing launchers separately on an isolated local server:

```powershell
python -B tests/mysql_hr_validation_browser.py --mysqld "PATH_TO_MYSQLD"
python -B tests/mysql_employee_listing_browser.py --mysqld "PATH_TO_MYSQLD"
python -B tests/mysql_finance_functional_browser.py --mysqld "PATH_TO_MYSQLD"
```

Green CI does not approve production deployment, actual backup restoration,
migration 008 execution, lifecycle publication, Payroll integration or permission
grants. Those remain separate approval gates. Follow the
[HR deployment runbook](../docs/deployment/hr-reliability-008.md) before proposing
a company deployment. No workflow deploys, automatically migrates configured
databases, merges pull requests or grants roles.

## Business audit regression tests

Run from the project root using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m py_compile app.py audit_log_repository.py payroll_workflow_repository.py leave_repository.py purchase_request_repository.py expense_repository.py user_repository.py tests/test_business_audit.py
```

The suite uses standard-library unittest and the application's installed dependencies.
It imports the real Flask application, exercises its routes and permission decorators,
disables dotenv loading, supplies a test signing key, and blocks the MySQL connector.
Templates are mocked. No database records are read or changed.

## Automated coverage

All 17 action types are covered (activate and deactivate count separately):

| Module | Actions |
| --- | --- |
| Payroll | Submit for Approval; Return to Draft; Approve Payroll; Mark as Paid |
| Leave | Approve; Reject; Cancel |
| Procurement | Submit Purchase Request; Approve; Reject |
| Finance | Approve Expense; Mark Expense as Paid |
| Administration | Create User; Activate User; Deactivate User; Reset Password; Update Role Permissions |

Each action verifies exactly one audit repository invocation with the acting user,
module, action, entity type, and readable identifier. Sensitive sentinel values in
forms, session data, and returned records must not appear in the audit arguments.
Unauthenticated and insufficient-permission requests, business validation exceptions,
business exceptions, and audit storage failures are covered for every action.

Separate per-action transaction tests execute the real business and audit write
repositories with distinct mocked connections. They verify commit-before-audit,
business rollback on commit failure with no audit attempt, and audit rollback without
business rollback on audit insert failure. Payroll readiness validation is stubbed;
these tests verify audit boundaries rather than payroll calculations. Workflow
repositories also reject a simulated repeat of an already completed transition.

Additional tests cover procurement false returns, invalid forms and permissions,
missing rejection reasons, budget blocks, protected accounts/roles, read-only forms,
and missing or failed display-identifier lookups with internal-ID fallback.

## Review findings and limits

- Business and audit transactions use separate connections. Audit failure can leave
  a committed business action without an audit row; this matches the existing helper's
  best-effort behavior. There is no retry or exactly-once delivery across crashes.
- Each successful request invokes the audit writer once. Payroll/leave state locks,
  finance state locks, and procurement conditional updates reject repeated completed
  transitions. Administration operations may validly run multiple times, each with
  its own event. Concurrent request/idempotency behavior is not proven by mocks.
- Payroll, leave, and finance perform one extra display lookup after each successful
  action (nine action types). Procurement and administration reuse loaded values.
  Lookup failure falls back to the internal ID. No new lookup/refactoring is needed
  for this verification task.
- No audit integration defects were found by this suite. Runtime application code
  and UI were unchanged during this testing task.

## Executed disposable MySQL smoke checks (2026-10-16)

```powershell
.\.venv\Scripts\python.exe -u tests/mysql_audit_smoke.py
```

The explicit runner starts a separate MySQL 8.0 server using `--no-defaults`, a new
temporary data directory, and a dynamically selected loopback port. It does not load
the ERP environment file or connect to the development server. It verifies the server
data directory before creating its test database and before shutting down. It applies
the repository's existing schema files only to its fresh database, seeds synthetic
fixtures, and removes its temporary directory after graceful shutdown. The local
Windows MySQL binary is required; use `--mysqld` to override its path.

Passed against MySQL 8.0.46:

- All 17 real business routes persist exactly one event with the expected actor,
  module, action, entity, readable identifier, and a timestamp near database NOW().
  Real business repositories, identifier lookups, audit writer, and Jinja templates
  run without mocks. Sensitive sentinel values do not appear in the persisted events.
- Unauthorized requests produce no events for all 17 actions; repeated completed
  transitions produce no additional events for the 12 workflow action types.
- Invalid user creation and a real duplicate-key business transaction produce no
  success audit event.
- Two simultaneous requests produce exactly one event for each of payroll approval,
  payroll payment, leave approval, purchase approval, expense approval, and expense
  payment. These are bounded smoke checks, not a sustained concurrency/load test.
- A real trigger-induced audit SQL insert failure leaves the expense approval
  committed and produces no audit row. The test trigger is removed afterward.
- Persisted module/action/date filters, readable-ID search, inclusive end dates,
  newest-first ordering with ID tie-breaking, page permissions, empty results,
  real HTML rendering, and (originally) the 500-row cap/banner passed. The current
  suite instead verifies bounded pages and traversal of all 501 fixture matches.

That initial smoke-testing checkpoint preceded Audit Logs pagination. The current
reader uses 25/50/100-record pages without discarding older matches; see the
[Audit Logs reading contract](../AUDIT_LOG_READING.md) and checks below.
The server was stopped and temporary test data removed. Production/development
records were never accessed or changed.

## Remaining manual browser checklist

The initial checkpoint used Flask HTML checks. The dedicated disposable Chrome
workflow below now checks navigation and permission denial. For visual review on
a test instance:

1. Open Audit Logs and visually check the table, actor, target, timestamps, and ordering.
2. Combine search, module/action, and date filters; clear filters; check empty results.
3. With over 500 matches, select 25/50/100 rows and reach the oldest records;
   check matching totals, empty states, and preserved filters across pages.
4. Complete a representative action and confirm its row appears after refresh;
   verify an account without `audit_logs.view` cannot open the page.


## CSRF regression coverage

Run all Python and JavaScript tests and both available disposable MySQL suites:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
.venv\Scripts\python.exe tests/mysql_audit_smoke.py
.venv\Scripts\python.exe tests/mysql_security_smoke.py
.venv\Scripts\python.exe -m pip check
```

`security_helpers.CSRFClient` generates a genuine Flask-WTF token for the actual
client session and submits it as a header. This fixture does not disable CSRF or
bypass the extension. Rejection tests use unmodified Flask test clients instead.
The audit integration's real approval, payment and administration routes now all
submit valid tokens. Security integration also exercises rendered login/logout
fields and expired-token recovery against synthetic MySQL records, confirming
rejected requests do not change supplier state, last-login state, or audit counts.

Static coverage checks verify each of the original 86 POST forms plus all three
new POST form sources includes exactly one shared token partial. Dynamic tests
reject missing/invalid tokens on all 87 POST-capable routes. A minimal test app
also covers PUT/PATCH/DELETE and stable receipt-UUID recovery without importing or
changing the separate procurement branch. No CSRF exemptions are permitted.

## Employee and Department business auditing (Step 4B.2)

Run the boundary tests and real database integration from the project root:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p test_hr_audit.py -v
.venv\Scripts\python.exe -u tests/mysql_hr_audit_smoke.py
.venv\Scripts\python.exe -u tests/mysql_hr_validation_browser.py
```

The MySQL runner uses the existing fresh-server harness, verifies its temporary
`@@datadir`, and seeds only synthetic HR records. The Chrome runner uses the same
disposable security-review server and additionally verifies persisted HR audit
actions and revision metadata after native form submissions and stale-tab conflicts.
Neither runner loads the configured company database connection.

The route calls the existing central audit helper after the business repository
returns from commit. CREATE uses the returned numeric identity and the schema's
initial revision 1. UPDATE and changed Department status actions use the returned
committed revision; the old revision is one less under the existing increment
contract. Ordinary saves, including unchanged values or employment-status changes,
emit one UPDATE attempt. Department status no-ops emit none. Descriptions contain
only the numeric identity, action wording and revision numbers; no extra lookup is
performed. Audit viewing permission is independent of HR write permissions.

Delivery remains best effort. A separate audit transaction can fail after the
business transaction succeeds. A process failure after commit and before audit
recording can leave a committed action unaudited. A lost commit acknowledgment can
also leave a committed action without an audit attempt: an exception is not proof
of rollback. The disposable test explicitly commits then raises to demonstrate
this case. There is no automatic retry, durable outbox, or exactly-once guarantee.

## Schema compatibility admission

Run `python -B tests/mysql_schema_compatibility_smoke.py` for the real gate on a
verified disposable server. Run `python -m unittest discover -s tests -p test_schema_compatibility.py`
for capability, cache, HTTP and failure-handling unit tests. See
[deployment requirements](../docs/deployment/hr-reliability-008.md) for fixture boundaries.

## Attendance Management

See [Attendance reliability](../ATTENDANCE_MANAGEMENT.md) for validation, pagination,
manual business audits, transaction/storage requirements and remaining policy limits.
Run `python -m unittest discover -s tests -p test_attendance.py -v`,
`python -B tests/mysql_attendance_smoke.py` and
`python -B tests/mysql_attendance_browser.py` with a verified local MySQL binary.
The smoke suite is discovered automatically by the existing CI helper.
Attendance Add/Edit share one CSRF-protected template; the source-form count test
reflects that deduplication, and route/browser tests verify the actual tokens.

## Disposable MySQL shutdown safety

The shared `mysql_audit_smoke.py` launcher starts Windows MySQL with `--no-monitor`
so the held subprocess handle belongs to the server, rather than its restart
monitor. Before tests and again before SQL `SHUTDOWN`, it verifies `@@datadir`
and the data-directory PID file against the owned subprocess. No configured
company database or process-name-based termination is used.

Graceful shutdown has a 20-second bound. A timeout prints server diagnostics and
terminates only the previously verified subprocess, with bounded 5-second waits
for terminate/kill. Successful fallback is explicitly logged. Failed termination,
unverified identity, or unexpected process exit fails the suite and retains its
directory and server log for investigation. Files are deleted only after confirmed
process exit; transient Windows deletion errors get at most three seconds of
retries and persistent failures remain failures. Assertion failures still propagate
after teardown. There is no automatic temporary-directory finalizer that could
delete files from a server left running.

Run `python -m unittest discover -s tests -p test_mysql_cleanup.py -v` for isolation,
termination failure and directory-retention checks. Native verification should
repeat `python -B tests/mysql_inventory_reporting_smoke.py`, run the Attendance
suite, and exercise teardown after an intentional assertion failure. Successful
development/CI runs do not authorize company database deployment.

## Leave Management

See [Leave reliability](../LEAVE_MANAGEMENT.md) for the effective approval rules,
transaction/overlap protection, listing filters and limitations. Run
`python -m unittest discover -s tests -p test_leave.py -v`,
`python -B tests/mysql_leave_smoke.py` and
`python -B tests/mysql_leave_browser.py` with a verified local MySQL binary.
The new smoke suite is automatically discovered by CI. The existing business-audit
fixtures retain their exact audit/commit assertions and now expect explicit 409
responses for finalized or losing concurrent Leave transitions. Native Chrome
remains a separate local check and does not authorize company deployment.

## IT Help Desk

See [Help Desk reliability](../HELP_DESK_MANAGEMENT.md) for validation, retained
forms, workflow/history transactions, filtered pagination, best-effort auditing and
limitations. Run `python -m unittest discover -s tests -p test_help_desk.py -v`,
`python -B tests/mysql_helpdesk_smoke.py` and
`python -B tests/mysql_helpdesk_browser.py`. The smoke suite is automatically
discovered by CI; Chrome remains a separate local check. All fixtures use only
fresh verified disposable databases, never company connection settings.


## Audit Logs read-only search and pagination

See [AUDIT_LOG_READING.md](../AUDIT_LOG_READING.md) for filter, snapshot, privacy
and compatibility contracts. These checks never use configured company databases:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_audit_log_reading.py -q
.venv/Scripts/python.exe -u -B tests/mysql_audit_log_reading_smoke.py
.venv/Scripts/python.exe -u -B tests/mysql_audit_log_reading_browser.py
```

The 21 unit tests cover filter validation, parameter binding, read-only cleanup,
HTTP errors, escaping, permissions and schema admission. The disposable MySQL
suite traverses 5,005 timestamp-tied historical events, tests all page sizes,
counts, inclusive dates, literal wildcard/injection searches, unknown/invalid
filters, authorization revocation, missing/non-InnoDB storage, read failures and
unchanged business/audit/grant snapshots. A deliberate concurrent synthetic
insert proves count/rows/options share a snapshot and a fresh request sees it.
The existing business-audit suite retains its write/commit checks and now
traverses every one of its 501 matching events instead of asserting a display cap.

The Chrome wrapper uses the existing isolated security runner, adds 1,005
historical events, and checks filter-preserving links, page-size form submission,
counts, oldest rows, invalid filters, escaped descriptions, privacy headers and
denied access. It verifies those historical rows remain unchanged. It requires
local native Chrome and is not claimed as hosted CI coverage. The shared runner
also checks cross-module CSRF, authentication and IT authorization behavior.
All `mysql_*_smoke.py` suites are discovered automatically by the CI MySQL job;
the browser wrapper is separate. No successful check authorizes deployment.


## Warehouse reliability

See [WAREHOUSE_RELIABILITY.md](../WAREHOUSE_RELIABILITY.md) for contracts and rollout
limitations. Run focused checks against synthetic data only:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_warehouse_reliability.py -q
.venv/Scripts/python.exe -u -B tests/mysql_warehouse_smoke.py
.venv/Scripts/python.exe -u -B tests/mysql_warehouse_browser.py
```

The 14 focused unit tests cover schema bounds, normalized text/IDs, rejected filters,
parameter binding, snapshot count/page ordering, transaction cleanup, missing/no-op
writes, retained escaped forms, safe post-commit audits and security boundaries.
The disposable suite checks 1,005 historical warehouses, all page sizes, filtered
counts, a concurrent snapshot insert, real unique-key races, identical edit/status
races, trigger/commit failure rollback, uncertain commit reconciliation, audit SQL
failure isolation and unchanged historical stock/movement data. It observes real
InnoDB lock waits in both stock/status orders and between Goods Receiving and
status changes. Stock-holding deactivation remains allowed. Existing Inventory
master tests retain their assertions with explicit changed-edit results and new
Warehouse 400/503 handling; other inventory behavior remains unchanged.

The Chrome wrapper checks listing/filter/page controls, retained/escaped validation
and duplicate forms, create/edit, no-op edits and repeated status requests, viewer
controls and authorization, CSRF and exact persisted audits. It also runs the
existing cross-module security/IT browser checks and verifies seeded historical
warehouse rows remain unchanged. The shared wrapper performs only synthetic DB
setup; its viewer grant is a test fixture, not a production permission change.
Native Chrome remains a separate local check. `mysql_warehouse_smoke.py` is picked
up automatically by the existing CI suite discovery. Tests do not approve deployment.


## Department Budget management

See [BUDGET_MANAGEMENT.md](../BUDGET_MANAGEMENT.md) for filters, unchanged financial
rules, audit boundaries and limitations. Commands use synthetic data only:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_budget_management.py -q
.venv/Scripts/python.exe -u -B tests/mysql_budget_management_smoke.py
.venv/Scripts/python.exe -u -B tests/mysql_finance_functional_browser.py
```

The 14 focused unit tests cover strict filters, exact existing money/year bounds,
notes, duplicate form fields, resource cleanup, transaction results, no-op/missing
edits, snapshot summary/page SQL binding, retained/escaped forms and security guards.
The disposable suite checks 1,005 historical budgets, 25/50/100 pages, all-match
sums, equivalence to legacy paid-only totals, inactive Department eligibility,
literal search excluding notes, read snapshots during a real paid-expense insert,
actual duplicate/edit/Department lock waits, real non-InnoDB storage rejection,
no precommit audit, rollback, lost
commit acknowledgments, audit SQL failure isolation, permissions and CSRF. Existing
Finance payment suites continue to verify key moves, creation races, both edit/pay
orders and the existing below-paid-spending reduction behavior. They are not mocks.

The existing Finance Chrome runner now also loads `browser_budget_management.cjs`.
It retains the expense correction/usage-boundary/viewer checks, and verifies Budget
pagination, full filtered cards, historical rows, strict invalid filters, retained
amount/year/notes, duplicate and unchanged edits, safe audits, viewer forgery and
CSRF rejection. It checks exactly one CREATE/UPDATE and unchanged historical Budget
fixtures. Existing invalid-year tests now expect 400 with no broader result, rather
than the previous redirect to the current year. This changes input handling, not
financial formulas. Browser checks remain local-only. The new SQL suite is picked
up automatically by existing CI discovery; no workflow/deployment changes are made.


## Inventory Items management

See [INVENTORY_ITEMS_MANAGEMENT.md](../INVENTORY_ITEMS_MANAGEMENT.md) for the listing,
write/audit contract, unchanged integrations and unit-of-measure policy question.

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_inventory_items.py -q
.venv/Scripts/python.exe -B tests/mysql_inventory_items_smoke.py
.venv/Scripts/python.exe -B tests/mysql_inventory_items_browser.py
```

The focused unit suite checks strict filters, SQL binding, counts, no-op/missing
writes, cursor cleanup, retained/escaped values and security. Disposable MySQL
covers 1,005 tied-name rows, 25/50/100 traversal, snapshot counts during a concurrent
insert, observed duplicate/edit/status locks, rollback, uncertain commits, audit
failure isolation and unchanged stock/movement history. Native Chrome verifies
pagination/filter links, empty/invalid results, retained raw input, duplicate/no-op
edits, explicit status replay and viewer/CSRF denial. Its wrapper verifies exactly
four committed Item audit actions and unchanged historical fixtures. The smoke
suite is included by existing CI discovery; Chrome is local-only. No deployment,
production grants or schema migration is performed by this feature.


## Inventory Categories management

See [INVENTORY_CATEGORIES_MANAGEMENT.md](../INVENTORY_CATEGORIES_MANAGEMENT.md) for
filter, validation, audit, assignment and concurrency contracts and limitations.

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_inventory_categories.py -q
.venv/Scripts/python.exe -B tests/mysql_inventory_categories_smoke.py
.venv/Scripts/python.exe -B tests/mysql_inventory_categories_browser.py
```

Focused unit fixtures block company DB access. Disposable MySQL checks 1,005
categories, 25/50/100 traversal, consistent snapshots, unique code/name handling,
edit/status no-ops and rollback, uncertain commits, audit failure isolation and
observed item assignment/deactivation lock waits in both orders. Chrome checks
retained escaped forms, filtered pagination, explicit status retries, viewer/CSRF
rejection and four persisted audit actions without historical assignment changes.
The existing master smoke expects generic 503 on category SQL failure, with its
unchanged-data assertion preserved. New SQL smoke is discovered automatically by
CI; Chrome remains local-only. Fixture grants/schema setup apply only to the fresh
verified disposable server, never company databases.


## Supplier management

See [SUPPLIER_MANAGEMENT.md](../SUPPLIER_MANAGEMENT.md) for unchanged required-field
policy, existing email/PO consistency questions, listing/write/audit contracts and
remaining limitations.

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_supplier_management.py -q
.venv/Scripts/python.exe -B tests/mysql_supplier_management_smoke.py
.venv/Scripts/python.exe -B tests/mysql_supplier_management_browser.py
```

Focused unit fixtures forbid company DB access. Disposable SQL checks 1,005
same-name suppliers, literal/combined/invalid filters, 25/50/100 pages, consistent
count/rows under concurrent insert, observed duplicate/edit/status/Finance locks,
rollback, uncertain commits, audit failure isolation and historical PO/expense
relationships. Native Chrome verifies retained escaped fields, explicit status
replay, security and optional contact/email/phone/address submission. Its wrapper
checks four changed audit actions and unchanged historical fixtures/POs. Session
security fixtures now mock the paged supplier reader while preserving existing
authorization assertions. SQL smoke is auto-discovered by CI; Chrome is local-only.
No production grants, migrations or deployment are performed.


## Finance Expense Categories management

See [EXPENSE_CATEGORIES_MANAGEMENT.md](../EXPENSE_CATEGORIES_MANAGEMENT.md) for
listing/write contracts, unchanged helper/reference rules, storage requirements
and limitations.

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_expense_category_management.py -q
.venv/Scripts/python.exe -B tests/mysql_expense_category_management_smoke.py
.venv/Scripts/python.exe -B tests/mysql_expense_category_management_browser.py
```

Unit fixtures forbid company DB access. The disposable SQL suite covers 1,005
same-name records, filtered 25/50/100 traversal, snapshot counts under inserts,
duplicate/edit/status lock waits, both expense reference/deactivation orders,
no-op/rollback/uncertain commits, audit failure isolation, history and active-only
eligibility preservation, and actual MyISAM rejection without repair. Chrome
verifies retained escaped values, native correction, duplicate/no-op edits, status
replay, security, four persisted audit actions and unchanged historical expenses.
The Finance audit suite expects 404 for a category lost before a status write,
retaining its no-success-audit assertion. Existing CI discovers the SQL smoke;
Chrome is local-only. No company DB, migration or production grants are used.
