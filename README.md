# Company Operations ERP System

A modular Enterprise Resource Planning (ERP) system built with Python, Flask, MySQL, Bootstrap, and JavaScript.

The system is designed to centralize several company operations into one application, including human resources, inventory, procurement, IT asset management, expenses, reporting, user management, and audit logging.

## Planned Modules

- User Authentication
- Roles and Permissions
- Dashboard
- Departments
- Employee Management
- Attendance Management
- Leave Management
- Inventory Management
- Warehouse Management
- Supplier Management
- Purchase Requests
- Purchase Orders
- IT Asset Management
- Help Desk Ticketing
- Expense Management
- Reports and Analytics
- Audit Logs

## Technology Stack

- Python
- Flask
- MySQL
- HTML
- Bootstrap
- CSS
- JavaScript
- Chart.js
- openpyxl

## Project Status

🚧 Currently under development.

## Session security and deployment

Authenticated application requests load the active user, current role and current
permissions with one joined MySQL query. Decorators and navigation share this
request-local state. Cookie permissions are ignored and removed. Anonymous
requests and static assets do not trigger this query. Authorization query failure
returns HTTP 503 and cannot authorize a business operation using cached rights.

Session inactivity expires after 30 minutes and absolute login age after 8 hours.
Configure positive integer seconds with `ERP_SESSION_IDLE_SECONDS` and
`ERP_SESSION_ABSOLUTE_SECONDS`. Activity refreshes only the idle timestamp; it does
not move the login time. Cookies remain browser-session cookies. Legacy sessions
without the new security metadata require a one-time reauthentication. All workers
must run the new code and use the same stable signing secret and synchronized clocks.
No permission names, seeded role assignments or business policies were changed.

An HMAC credential marker binds each session to its user ID and stored password
hash. The password hash is never included in the cookie or logs. Password changes
invalidate all existing sessions on their next application request. Disabled or
deleted accounts are rejected, and committed role/permission changes apply to the
next authorization lookup. This is not a transaction-level revocation guarantee:
a request authorized before a concurrent revocation may still finish.

Set the following explicitly in the deployment environment (see `.env.example`):

| Setting | Local HTTP development | Production HTTPS |
| --- | --- | --- |
| `ERP_ENV` | `development` | `production` |
| `ERP_DEBUG` | `false`, or explicit `true` for local debugging | `false` required |
| Session `Secure` cookie | Disabled | Enforced |
| Session `HttpOnly` cookie | Enabled | Enabled |
| Session `SameSite` cookie | `Lax` | `Lax` |

`ERP_ENV` defaults to development; do not rely on this default in deployment.
Production refuses debug mode and missing/short/example signing keys. Generate a
random `SECRET_KEY` with at least 32 bytes of entropy, store it outside source
control, and supply it consistently to every worker. The minimum-length check is
not an entropy guarantee. Changing the signing key invalidates existing cookies.
Do not expose `python app.py` or Flask's development server as a production server;
use a supported WSGI server behind verified HTTPS termination. External hosting
must not override production DEBUG settings or enable a debugger.

TLS, public host restrictions, proxy topology, HSTS and WSGI settings cannot be
verified from this repository. No `ProxyFix` trust is enabled automatically; if a
reverse proxy is used, configure only its verified forwarded-header hop counts.
Production Secure cookies will not work over plain HTTP. Local HTTP testing should
retain the development/testing profile. No database migration is required.

Limitations: logout still uses the existing GET route and best-effort audit helper;
CSRF protection and POST logout are deferred to Security Part 2. During an
authorization outage, logout may clear the local session without fresh permissions;
this exception grants no business access, and audit storage failure cannot prevent
logout. Server-side individual-session revocation is not provided: a copied valid
cookie can remain usable until expiry or credential change, and disabling then
reactivating an account can make an unexpired copied cookie usable again. Browser
session restore may retain cookies; server-side idle/absolute limits still apply.

Run the automated checks without using company database settings:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
.venv\Scripts\python.exe tests/mysql_audit_smoke.py
.venv\Scripts\python.exe tests/mysql_security_smoke.py
```

Each MySQL runner creates and verifies its own disposable server and synthetic
records. No development/production schema or records are used. Browser verification
still needs to confirm real HTTPS cookie behavior, local HTTP login, multiple-tab
expiry/re-login, and the actual WSGI/proxy configuration before deployment.
