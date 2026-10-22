# Navigation permissions and dashboard reliability

Attendance and Leave navigation follow `attendance.view` and `leave.view`
independently. Administration grants are not required or added. The six navigation
groups, active destinations, breadcrumbs, responsive controller and protected POST
logout are preserved. Route permissions remain authoritative.

## Permission-scoped reads

The authenticated dashboard route passes the refreshed request-local permission
set to `get_dashboard_summary(permissions)`. There is no implicit load-all default.
Only sections with their own view permission execute a reader; `dashboard.view`
does not grant access to another section. The existing login-only dashboard route
policy and empty-dashboard message remain unchanged.

The existing `today` and nine section keys remain. Available sections retain every
existing count key and status definition. Unauthorized sections have value `None`
and are not rendered. Authorized unavailable sections also have value `None` and
render a labelled unavailable card, never zero totals or "no paid payroll" claims.
Healthy cards retain their existing content and links. No Payroll/Lifecycle policy,
permission, financial formula or operational feature is enabled by these reads.

Each permitted section uses one parameterized SQL aggregate and returns one row;
no complete employee, expense, inventory, ticket or payroll lists are materialized.
SQL source/column/alias fragments are static application definitions, not request
input. Counts retain the original readers' INNER JOIN row eligibility; optional
label-only LEFT JOINs are omitted. Inventory active counts retain nonzero Boolean
semantics. Employment status normalization retains Python whitespace stripping,
uppercase and exact status comparison, including Unicode whitespace and accents.
Other stored state/priority fields retain their canonical ENUM definitions.

Attendance Today binds a single application-host `date.today()` value captured
once per summary, preserving existing date semantics rather than changing to the
database date or another timezone. Other cards remain all dates. Pending approval
counts retain SUBMITTED PR, APPROVED expense and PROCESSING Payroll semantics.
Help Desk open means OPEN/IN_PROGRESS, with urgent restricted to those states.

Payroll adds one `LIMIT 1` query in the same read-only REPEATABLE READ snapshot as
its aggregate. Latest paid means start date descending then period ID descending,
not payment date. The returned period fields/labels match the original reader.
Every section ends its snapshot and closes the cursor/connection before rendering.
No dashboard read writes business data or emits a business audit.

## Failure boundaries

Only missing module table/column errors (1146/1054) become unavailable cards, with
a section name and numeric error code logged for operators. Responses do not expose
SQL, database identifiers, exception text or credentials. Other SQL errors,
database-level permission denial, connectivity and cleanup failures produce a
generic 503 through the existing service-unavailable handling. They are not hidden
as empty/zero/unavailable-module results. Authentication/authorization failures and
the global schema-admission guard still execute before the dashboard and retain
their existing denial/fail-closed behavior. No schema gate is bypassed or weakened.

A missing Payroll table is never queried for a non-Payroll user. An authorized
Payroll user sees an unavailable Payroll section while available sections remain
usable. Global core-schema incompatibility still blocks the whole request, even
if that user would not display the affected module. Independent section snapshots
can reflect different commits; there is no cross-module point-in-time certificate.

## Verification and limitations

- Permission-matrix navigation tests now expect Attendance/Leave without an
  Administration grant and retain independent destination/active-state coverage.
- `test_dashboard_reliability.py` covers permission-scoped reader calls, bounded
  read-only results, date binding, unavailable rendering, error classification,
  current permission refresh, anonymous denial and fundamental schema/auth failures.
- `mysql_dashboard_reliability_smoke.py` uses a verified fresh server and compares
  every aggregate and latest paid record against existing list readers, including
  empty results, 1,005 items and Unicode employment states. It verifies fetchone-only
  results, a concurrent Payroll snapshot, missing Payroll/Leave storage, no Payroll
  reader for HR users, unchanged business/audit/grant snapshots and security refresh.
- `mysql_navigation_dashboard_browser.py` composes existing security/IT Chrome
  checks with an HR Manager fixture without Administration/Payroll grants. It
  verifies native Attendance/Leave links, active states/breadcrumbs, denied forged
  Administration POSTs and explicit unavailable Payroll for an authorized operator.
  Only synthetic test storage is temporarily renamed; history/grants are checked.
- The Finance reporting smoke now explicitly requests only Finance dashboard data,
  retaining all-date status-count assertions without mocking unrelated list readers.

Aggregation bounds transferred rows and Python memory, not the number of database
rows scanned. Exact counts/normalization/joins still require representative staging
plans and load measurements. Multiple authorized sections open separate guarded
connections; a failure detected in any fundamental connection fails the request.
The compatibility lease and external-writer limitations are unchanged. Native
Chrome is separate from hosted CI; production HTTPS, scale and visual acceptance
remain deployment work. No migrations, production grants or company DB operations
are performed by this change. Existing smoke discovery includes the new suite.
