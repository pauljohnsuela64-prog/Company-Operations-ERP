# ERP CI #47: four misleading database annotations

## Evidence and exact cause

Inspected the complete Python job log for [ERP CI #47](https://github.com/pauljohnsuela64-prog/Company-Operations-ERP/actions/runs/40064846013),
run ID `40064846013`, Python job `120785810452`, attempt 1, commit
`5a2e3ed8361719be3ea6ecaabd71a738f28b2abb`. The local fix branch starts
at that same commit. All three hosted jobs concluded success.

All four annotations arose in step 7, **Run complete unittest suite**, command
`python -m unittest discover -s tests -q`. The job ended with 544 tests and `OK`.
They did not come from package installation, syntax checks or MySQL integration.

Each traceback follows the same path:

`app.record_audit_event` (app.py:525) → `create_audit_log`
(audit_log_repository.py:25) → `database.get_connection` (database.py:79) →
`connection_options` (database.py:28) → `SchemaUnavailable`.

The hosted `-q` log does not include individual test names. A diagnostic local
reproduction tracked the active unittest ID for every audit error, with dotenv
disabled and DB environment settings absent as in CI. All four identified
`test_hr_validation.HRRouteTests.test_desired_state_is_explicit_and_repeatable`.
That test submits `/departments/1/status` four times:

| Annotation timestamp in hosted log (UTC) | Submitted state | Audit action |
| --- | --- | --- |
| 2026-10-24T05:04:58.1544002Z | `0` | DEACTIVATE |
| 2026-10-24T05:04:58.1563799Z | `0` | DEACTIVATE |
| 2026-10-24T05:04:58.1574957Z | `1` | ACTIVATE |
| 2026-10-24T05:04:58.1587479Z | `1` | ACTIVATE |

The test mocks the business write to return a changed `HRWriteResult` for each
request, but omitted a mock for audit persistence. The production best-effort
audit wrapper therefore tried the real connection path. Missing CI database
configuration correctly raised before a connector connection was attempted.
The wrapper correctly logged the exception without undoing the simulated business
success, and the route assertions still passed.

These are unintended unit-test dependency escapes, rather than intentional
negative-security-test exceptions or proof of an incompatible demo database.
With local settings present, the same omission instead reaches the suite's
connector tripwire and logs `Company DB forbidden`; it still must be fixed.

The pinned setup-python action registers its [Python problem matcher](https://github.com/actions/setup-python/blob/5fda3b95a4ea91299a34e894583c3862153e4b97/.github/python.json).
Its two-line regex matches a `File ..., line ...` traceback frame followed by
`raise SomeException('message')`. It does not check unittest's final result.
Applying that exact matcher to the complete hosted log reproduces exactly four
matches for `database.py:28`, message `Database compatibility unavailable.`
The hosted log contains the corresponding four `##[error]` lines.

## Fix

Only `tests/test_hr_validation.py` changes executable behavior, inside this one
test method. It now mocks `app.create_audit_log` at the same dependency boundary
as the existing dedicated HR audit tests. Each simulated changed write must emit
one audit call with the correct action and target. Invalid status forms must
invoke neither business persistence nor audit persistence.

`assertNoLogs(app.logger, level='ERROR')` makes an unexpected error log fail the
test. It does not ignore error records. Existing intentional audit-outage tests
retain their scoped `assertLogs` assertions. No logger is disabled, no stderr
stream is silenced, and no CI matcher is removed.

`database.py`, schema admission, audit production behavior, authentication,
authorization, CSRF and `.github/workflows/erp-ci.yml` are unchanged.

## Verification

- Complete Python discovery: **544 passed**, with no audit-write or database
  compatibility traceback in its output.
- JavaScript navigation: **11 passed**; all 30 JavaScript syntax checks passed.
- Python compilation: 183 tracked Python files; Jinja syntax: 110 templates.
- `pip check` and `git diff --check`: passed.
- Disposable `mysql_hr_audit_smoke.py`: passed, including deliberate audit storage
  failure, rollback/commit handling, concurrent HR writes and permissions.
- Disposable `mysql_schema_compatibility_smoke.py`: passed, including unavailable
  metadata/connectivity, wrong selected database, missing constraints/permission
  codes, blocked business handlers/direct CRUD, CSRF and anonymous access.
- A temporary failing unittest fixture, run through the unchanged CI discovery
  command, produced both an assertion failure and an unexpected RuntimeError;
  the process exited **1** and retained failure diagnostics. The workflow uses
  that command directly with Bash `-e` and no `continue-on-error` or masking, so
  genuine test failures still fail the job.
- The working loopback demo still returned 200 for live/ready/login and authorized
  dashboard/module access. Normal synthetic login, permission rejection and CSRF
  rejection passed. This HTTP verification only performs the app's usual login
  metadata updates; no demo schema, business fixtures, budgets, records or account
  permissions were changed by this investigation. No initialization/seeding ran.

All integration tests used their verified disposable servers, not either
persistent ERP database. The original database/account and local secret files
were not modified. Pre-existing uncommitted demo setup files were preserved.

## Final publication review

Fetched `origin/main` and verified the branch base, merge-base and local `main`
all match `5a2e3ed8361719be3ea6ecaabd71a738f28b2abb`. The publication commit
contains only this investigation report and `tests/test_hr_validation.py`.
The known pre-existing `.gitignore` change and untracked local demo setup files
remain outside that commit. Local secret files are untracked, and scanning the
tracked files and proposed report found none of the local passwords/signing keys.

The final review repeated all 544 Python tests, all 11 navigation tests, all 30
JavaScript syntax checks, Python/Jinja syntax, dependency checks and both relevant
disposable MySQL integration suites successfully. A separate mutation probe
injected an unexpected ERROR log into the corrected route test and confirmed
that its `assertNoLogs` assertion fails with exit 1. Temporary assertion-failure
and unexpected-exception probes also returned exit 1 with diagnostics retained.
No production or workflow file changed. The final review did not connect to or
modify either persistent ERP database.

Branch: `fix/ci-database-annotations`. A local publication commit is authorized
after successful final review; no push or merge was performed.
Hosted verification of the fix remains pending approval to push and run CI;
historical run #47's existing annotations are not removed by this local change.
