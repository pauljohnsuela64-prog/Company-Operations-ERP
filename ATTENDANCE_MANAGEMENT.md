# Attendance Management reliability

The Attendance list and manual Add/Edit routes retain `attendance.view` and
`attendance.manage`, existing account/session refresh, CSRF and schema admission.
No migration, role grant, production database operation or Payroll/lifecycle
integration is included. Deploy through a separately approved application rollout.

## Input and transaction guarantees

- Employee, acting user and record IDs must be positive signed-INT identities.
  Employee existence is checked with a shared lock inside the write transaction.
  Existing employment statuses do not add new eligibility restrictions.
- Dates use strict YYYY-MM-DD and MySQL's 1000-01-01 through 9999-12-31 range.
- Optional Time In/Out accept local HH:MM or HH:MM:SS, 00:00:00 through 23:59:59.
  MySQL TIME values are formatted with leading zeros and seconds on Edit and the
  listing; midnight is shown as 00:00:00 rather than a missing value. Blank
  times remain NULL. Timezone offsets, fractions, durations and 24:00 are rejected.
- Status remains one of PRESENT, LATE, ABSENT, ON_LEAVE or HALF_DAY. It is selected
  manually. No lateness threshold, shift duration, payroll value, automatic status,
  required-time combination, future-date cutoff or time ordering rule is inferred.
  A Time Out earlier than Time In is stored without interpreting an overnight shift.
- Notes are optional UTF-8 text, normalized at the outer whitespace, at most 255
  characters. Unsupported control characters and malformed Unicode are rejected.
  Duplicate submitted form fields are rejected. Rendered notes/inputs are escaped.
- Validation errors preserve submitted fields and show feedback without redirecting
  away. HTTP 400 is invalid input, 409 duplicate/reference/lock conflict, 404 a missing
  edit target, and 503 incompatible storage or an unconfirmed save. Dates/times that
  a browser considers invalid can display blank in native inputs; other form fields
  and server-side error feedback remain available for correction.

Create/Edit use explicit transactions and rollback on failures. Edit locks and
rechecks its target; a deleted record cannot silently report success. The existing
employee/date unique constraint arbitrates concurrent duplicate submissions. No
precheck is treated as a substitute for database uniqueness. Lock conflicts are
reported for explicit reload/review rather than automatically replaying a write.

Attendance operations check the existing table's InnoDB engine and full unique
employee/date index using read-only metadata. Incompatible storage fails closed;
there is no automatic conversion, repair or migration. Users receive a generic
unavailable message; operator logs identify the missing capability without notes
or credentials. Global schema admission for
merged HR/Inventory/Procurement capabilities remains unchanged. An operator must
review the actual target's table definitions under the normal deployment gate.

## Pagination and history

The list accepts 25, 50 or 100 rows per page (default 25). Employee/name/Department
search, date, status, Department and page size survive navigation links. Search is
a bounded literal substring: `%`, `_` and `!` are escaped rather than wildcard
operators. Invalid filters return feedback/400 instead of silently widening results.
Inactive Departments remain available for historical filtering.

A read-only REPEATABLE READ snapshot supplies filtered COUNT/status totals and the
bounded page together. Summary cards describe all matching rows, not only the page.
Ordering is date descending, employee surname/given name, then unique Attendance
ID. Pages use separate snapshots; intervening writes can move records between
pages. Oversized page numbers clamp to the final page; empty results have one empty
page. Existing records are not backfilled, recalculated or deleted. Legacy read
repository functions remain available for existing callers. Large OFFSET/count
costs and the Employee dropdown still need representative staging measurement;
this work does not redesign the Employee selector or unrelated dashboards.

## Central auditing and limits

After the repository returns a successful committed save, each manual create/save makes
one best-effort central audit attempt: ATTENDANCE / CREATE or UPDATE, numeric
Attendance identity, actor and bounded action description. Notes, names, times and
other personal details are excluded. An unchanged explicit Save is still a save
operation and receives one UPDATE attempt after commit. Failed writes, deleted
targets, duplicates and rejected requests emit no successful Attendance event.
Audit storage failure cannot reverse a committed business action.

Delivery is not durable or exactly once. A commit acknowledgment can be lost after
persistence; cleanup can also fail after a commit. In either case the request can
report an unconfirmed save and no success audit is attempted. Reconcile the persisted record before retrying. Missing audit
rows do not prove rollback. Direct SQL, legacy workers and existing automatic Leave
approval writes are not newly intercepted by this manual-route audit integration;
Leave retains its existing approval transaction and business audit behavior.

There is no optimistic stale-edit token or new schema revision column. Row locks
serialize saves but do not prevent a later form from replacing an earlier edit.
New concurrency-policy/schema work requires separate review. Coordinate deployment
of compatible workers and maintenance for privileged DDL. The application does
not fence external SQL or guarantee metadata cannot change concurrently.

## Verification

```powershell
python -m unittest discover -s tests -p test_attendance.py -v
python -B tests/mysql_attendance_smoke.py --mysqld "PATH_TO_MYSQLD"
python -B tests/mysql_attendance_browser.py --mysqld "PATH_TO_MYSQLD"
python -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
python -B scripts/ci_checks.py python
python -B scripts/ci_checks.py javascript
python -B scripts/ci_checks.py mysql
```

The new disposable suite preserves the real schema inspector/guard, verifies its
fresh loopback datadir, exercises non-strict SQL boundaries, pagination, duplicates,
concurrent creates, real rollback, missing targets, lost commit acknowledgment,
audit-store failures, storage incompatibility, auth/CSRF and Leave compatibility.
All schema corruption/fault fixtures use only the verified temporary database.

The native Chrome wrapper composes the existing synthetic security runner with
Attendance search/page size/navigation, retained and escaped validation feedback,
duplicate create, second-precision editing, manual status, CSRF and viewer denial.
It checks persisted actions and historical fixtures after browser completion.
Native browser execution does not certify production TLS, accessibility or scale.
The existing Actions MySQL discovery includes the new smoke suite automatically;
browser workflows remain local-only under the existing CI policy.
