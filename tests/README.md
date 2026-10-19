# Business audit regression tests

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
  real HTML rendering, and the 500-row cap/banner pass.

The Audit Logs implementation has **no pagination**: it displays the latest 500
matching records. The existing behavior was verified without adding pagination.
No confirmed audit defects or application changes resulted from smoke testing.
The server was stopped and temporary test data removed. Production/development
records were never accessed or changed.

## Remaining manual browser checklist

No interactive browser was used; Flask test-client checks validate rendered HTML.
On a test instance:

1. Open Audit Logs and visually check the table, actor, target, timestamps, and ordering.
2. Combine search, module/action, and date filters; clear filters; check empty results.
3. With over 500 matches, confirm the latest-500 notice and absence of pagination.
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
