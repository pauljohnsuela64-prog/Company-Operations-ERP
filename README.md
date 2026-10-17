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

Logout now requires a valid CSRF-protected POST and retains the best-effort audit
helper. GET /logout only renders confirmation and does not refresh, clear, or
otherwise change authentication metadata. During an authorization outage, POST
logout may clear the local session without fresh permissions;
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


## Application-wide CSRF protection (Security Part 2)

Install the pinned requirements before starting the application:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Flask-WTF `CSRFProtect` protects POST, PUT, PATCH and DELETE globally. No business
routes or blueprints are exempt. All 86 original POST forms include the shared
`templates/partials/csrf_field.html`, including standalone login. New navigation,
logout confirmation and explicit recovery forms also include it (89 source forms
in total). GET forms remain read-only. Logout adds the 87th POST-capable route;
all original URL paths and business permission checks are retained. No database
migration is needed. All business repositories and the separate procurement
feature branch are unchanged.

Tokens expire after one hour, remain usable across tabs, and are tied to the
current session. Successful login and logout clear the old session seed. HTML
responses and token-refresh responses are marked `Cache-Control: no-store`.
A missing, invalid or expired token produces HTTP 400 with no execution of the
business view. Authorization still runs first: invalid authentication can redirect
to login, and authorization outages can return 503, before CSRF validation runs.
Neither path authorizes a business mutation.

Expired forms are not automatically replayed. An explicit recovery form is offered
only after verifying that the expired token's signature and session seed still
match. It preserves all submitted values, duplicate fields and any opaque
`submission_id`, replacing only `csrf_token`. Password/secret-bearing and file
upload forms do not get payload-preserving recovery. Missing, malformed or
other-session tokens cannot get that recovery. The user must review the original
values and deliberately submit again. Recovery payloads are not persisted server-side or logged.

The receiving UUID and CSRF token are separate fields with separate purposes.
Middleware recovery is tested with a fixed delivery UUID and an idempotent test
handler. The actual feature/purchase-orders implementation is not on this branch;
its full integration must still be tested when the branches are combined. Keep its
submission UUID unchanged across retries; do not replace it while renewing CSRF.
Session expiry or reauthentication invalidates old CSRF tokens and requires user
recovery; do not automatically reopen/replay receiving as a new delivery when an
earlier result is uncertain.

There are no current fetch/XHR mutation calls. Future same-origin clients can read
`meta[name="csrf-token"]` and send `X-CSRFToken` (or `X-CSRF-Token`) on unsafe
requests. `GET /auth/csrf-token` returns a renewed signed token for the current
session as JSON, without invalidating other still-valid tab tokens. It is read-only
with respect to business data; it may create the session's CSRF seed. Do not send
tokens to external origins, enable cross-origin credential access, or globally
patch fetch. JSON failures return `error=csrf_failed` and HTTP 400; refreshing the
token must never automatically repeat an uncertain payment, approval or delivery.
HTTPS requests also retain Flask-WTF's same-origin Referer check. Verify the real
public origin and trusted proxy configuration rather than disabling that check.

Tests use real Flask-WTF-signed tokens, with CSRF enabled. Existing workflow
fixtures now attach valid token headers; rejection tests use raw browser-style
clients. Both disposable MySQL suites must continue to run with CSRF enabled.
Before deployment, test real HTTP/HTTPS cookies, two open tabs, expired-form
recovery, password re-entry, POST logout during an outage, and the receiving UUID
integration after combining branches. Forms opened before this rollout may need
to be reopened because they contain no CSRF field.
