# Company Operations ERP

Flask/MySQL ERP with a responsive navy/slate workspace. Assignments 1 (GUI) and
2 (cleanup/integrity) are merged. Assignment 3 independently verifies baseline
4b927555c5e76aa236bf9924895daec4c27198df. Readiness is assessed separately for
isolated synthetic demos, internal pilots and production; this is not production
certification or deployment authorization.

## Implemented modules

- Authentication, users/roles/permissions, dashboard and central audit viewing.
- Departments, Employees/revision conflicts, Attendance, Leave/balances and HR reports.
- Inventory categories/items, Warehouses, Stock In/Out, movements, reconciliation
  and reports with Decimal transactions and UUID duplicate protection.
- Suppliers, Purchase Requests/items/approval, Purchase Orders and partial/full
  Goods Receiving connected to stock.
- Finance expense categories, expenses, budgets, approvals/payments and exports.
- Payroll compensation, periods, entries, monthly calculation, adjustments,
  submit/return/approve/pay, paid payslips and reports. Salary/cutoff/pay-type and
  employment lifecycle policies are not certified for real salary processing.
- IT Assets registration/custody/return/maintenance/lifecycle/reports and Help Desk
  ticket creation/assignment/progression/resolution/closure with histories.

## Technology and safe synthetic verification

Python 3.14, Flask/Jinja, MySQL 8.0.16+ with enforced CHECKs and InnoDB, Bootstrap
5.3.8, CSS/JavaScript and openpyxl. Requirements are pinned in requirements.txt.
Node 24 runs navigation/CDP checks without npm dependencies. Local release checks
used MySQL Community 8.0.46 and Windows; see the test report for exact versions.

```powershell
py -3.14 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -B -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
.venv/Scripts/python.exe -B scripts/ci_checks.py python
.venv/Scripts/python.exe -B scripts/ci_checks.py javascript
.venv/Scripts/python.exe -B scripts/ci_checks.py mysql
.venv/Scripts/python.exe -B tests/mysql_payroll_freshness_audit.py
.venv/Scripts/python.exe -B tests/mysql_release_rehearsal.py
.venv/Scripts/python.exe -B tests/mysql_payroll_freshness_browser.py
```

MySQL runners create --no-defaults servers on dynamic loopback ports, verify their
selected datadir and held-child PID, seed synthetic records and stop only their own
server. They do not use company settings in .env. Investigate identity/cleanup
failures; never fall back to an existing server. scripts/ci_checks.py mysql
accepts --mysqld for an explicit installed executable, never a database endpoint.

Visual/accessibility suites require ERP_GUI_BOOTSTRAP_CSS pointing to trusted local
Bootstrap 5.3.8 CSS; visual suites also use ERP_GUI_SCREENSHOTS. They serve that
cached CSS and block other external resources. See ERP_V1_TEST_REPORT.md for
browser commands and coverage. Synthetic root/no-password connections and fixture
passwords are test-only. Do not run setup/connection-check scripts against
workstation defaults as a substitute for isolated tests.

For a separately authorized persistent development instance, provision a dedicated
synthetic database with explicit configuration and the reviewed schema/migrations.
The disposable runners demonstrate reproducible setup, not production provisioning.
Flask's development server is only suitable for an isolated local target.

## Security and integrity contracts

Supply SECRET_KEY and DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME explicitly.
ERP_ENV defaults to development; production must be explicit with ERP_DEBUG=false.
Production startup rejects missing/example/short signing keys and debug mode;
minimum length does not prove entropy. All workers need one stable secret and
synchronized clocks. Never put secrets or company data in Git.

Signed sessions use an HMAC credential marker rather than exposing password hashes.
Committed password/role/permission/active-status changes apply on the next request;
this is not retroactive cancellation of an in-flight authorized transaction.
Defaults: 30-minute idle and eight-hour absolute expiry, configurable via
ERP_SESSION_IDLE_SECONDS and ERP_SESSION_ABSOLUTE_SECONDS. Cookies are
HttpOnly/SameSite=Lax; production enforces Secure.

CSRF protects unsafe methods including login/logout. GET logout is confirmation;
POST requires a token. One-hour tokens support explicit signed expired-form
recovery without automatic business replay. Permitted values/UUIDs are retained;
password/secret/file forms do not receive payload-preserving recovery. Receiving
UUIDs and CSRF tokens serve different purposes: reconciliation retains the original
receiving identity and must not replay an uncertain payment or delivery automatically.

Explicit migration 010 adds durable Attendance generations and saved calculation
evidence under a shared Attendance/Leave/Payroll transaction guard. Stale/unknown
submit/approve/pay rejects; legacy evidence is not fabricated, APPROVED is not
automatically reopened and PAID history is preserved. Missing/incompatible structures
can block database-backed requests application-wide, including login. Startup never
automatically runs migrations.

Known limits: no per-device server-side session revocation, no automatic login rate
limiter/MFA, best-effort central audit durability, pinned external CDN CSS, and no
physical-device/full WCAG/production-capacity certification. See the known-issues
register for sensitive-data, authorization, deployment and policy boundaries.

## Deployment and release evidence

Do not expose Flask's development server/debugger publicly. An approved WSGI host,
verified TLS/proxy/host controls, managed secrets, least-privilege DB credentials,
backups/restore, monitoring and owner UAT are prerequisites. ProxyFix trust,
HSTS/CSP and public host controls are not enabled automatically. Production Secure
cookies do not work over plain HTTP.

Migration 010 requires approved backups, drained writers, schema validation,
explicit migration, coordinated worker deployment, readiness proof and deliberate
resumption. Mixed old/new/direct SQL writers are unsupported. DDL implicitly commits;
old-code rollback forfeits the new guarantee. APPROVED recovery, PAID correction,
salary/lifecycle, PR self-approval and historical UOM remain owner decisions.

- [Release readiness](ERP_V1_RELEASE_READINESS.md)
- [Final test report](ERP_V1_TEST_REPORT.md)
- [Known issues and decisions](ERP_V1_KNOWN_ISSUES.md)
- [Deployment checklist - not authorization](ERP_V1_DEPLOYMENT_CHECKLIST.md)
- [Development changelog](ERP_V1_CHANGELOG.md)
- [Progress and workflow matrix](ERP_V1_RELEASE_VERIFICATION_PROGRESS.md)
- [Route/permission inventory](docs/ERP_V1_ROUTE_PERMISSION_INVENTORY.csv)
- [Payroll freshness](PAYROLL_ATTENDANCE_FRESHNESS.md)
- [Migrations](database/migrations/README.md)
- [CI and focused tests](tests/README.md)

CI runs Python tests/syntax/dependencies, JavaScript syntax/navigation and discovered
MySQL smoke suites. Chrome/Edge visual/accessibility checks, the explicit original
freshness audit and new backup/restore rehearsal are separate local checks. Green
CI does not certify those checks or authorize deployment, release tags or company
migrations.
