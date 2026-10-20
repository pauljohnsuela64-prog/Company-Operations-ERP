# Help Desk reliability

Help Desk retains `helpdesk.view` / `helpdesk.manage`, existing account/session
refresh, CSRF and global database schema admission. No schema migration, grant,
company data operation, SLA, escalation, ownership rule, Payroll change or employment
lifecycle publication is included. Production deployment needs separate approval.

## Existing rules and duplicate definitions

The two definitions of `get_filtered_helpdesk_tickets` were identical; so were the
two definitions of `get_helpdesk_ticket_history`. Python used the later definition
of each. There is now one of each, retaining the legacy result fields, ordering,
filter arguments and wildcard-search behavior. Reports and Excel export readers
retain their existing behavior and formula-injection protection. The new HTTP
listing uses a separate bounded reader with literal search.

Workflow rules remain:

- Assign/reassign only OPEN or IN_PROGRESS tickets to an active user whose current
  role name is Super Admin or IT Manager. There is no new actor ownership rule.
- Start only OPEN tickets with a non-NULL assigned technician. Existing assignments
  are not newly revalidated for technician activity when starting/resolving/closing.
- Resolve only IN_PROGRESS tickets; close only RESOLVED tickets. CANCELLED remains
  a historical/readable status; this change adds no cancellation/reopening route.
- Any existing Employee can have a ticket, regardless of employment status. New
  tickets require an active category. Historical inactive categories/technicians
  remain visible and filterable.

## Validation and transaction boundaries

Ticket, Employee, category, Department, technician and actor IDs use positive signed
INT limits. Request fields and filters reject duplicate values. Priorities/statuses
use the existing enumerations. Subjects are required, at most 150 characters.
Descriptions/resolutions are required UTF-8 text within MySQL TEXT's 65,535-byte
capacity, with valid Unicode and no unsupported control characters. This is a
physical storage limit, not a ticket-length policy. Surrogate values, overflow and
non-strict SQL coercion are rejected before writes.

Create locks the Employee and derives the current Department snapshot inside the
transaction. An explicitly supplied non-NULL Department must still match. An inactive
Employee Department is retained; there is no new Department eligibility policy.
The category is checked under a shared row lock. Assignment checks and locks the
technician's active state and role before locking/rechecking the ticket. A concurrent
deactivation/role change cannot slip between an advisory precheck and the write.

All writes explicitly begin a transaction and inspect required InnoDB tables and
the full unique ticket-number index. Metadata inspection never repairs schemas.
Ticket number generation retains TMP-UUID then HD-ID conventions in one transaction.
Duplicate numbers, missing references and lock conflicts produce useful safe errors.
No content-based ticket deduplication or idempotency guarantee is invented.

Ticket state/assignment and its history row commit together. History failure rolls
back the ticket write. New creation gets a CREATED entry; existing history is not
backfilled or rewritten. Existing assignment/status action names and details remain,
including the first 255 characters of a resolution in ticket history. An explicit
assignment to the same eligible technician is now a no-op: no extra history or audit.
History ordering remains timestamp descending, then history ID descending.

HTTP 400 indicates invalid input/reference, 404 missing target, 409 workflow/number/
lock conflict, and 503 incompatible storage or an unconfirmed save. Form values are
retained and escaped on errors, including unavailable references. Manage-only users
do not gain full ticket/history viewing through error responses. Successful writes
keep existing redirects. Repeated start/resolve/close requests return 409.
If a missing/unavailable history table prevents an error page from loading,
the response remains a generic 503 rather than failing while rendering recovery.

## Central audit logs

After repository commit and cleanup return successfully, HTTP CREATE, changed
ASSIGN, START, RESOLVE and CLOSE each attempt one central `HELP_DESK` business audit
with the numeric `HELPDESK_TICKET` identity. Descriptions contain only the ticket ID
and action. Subjects, descriptions, resolutions and technician/Employee names are
excluded. Denied/invalid/failed/no-op operations produce no success audit attempt.
An audit storage failure cannot reverse the committed ticket/history transaction.

Central auditing is best effort, without durable/exactly-once delivery. Direct
repository calls do not add central HTTP business audits. A lost COMMIT acknowledgment
or postcommit cleanup failure can leave committed ticket/history while returning
503 and creating no success audit. Reload and inspect number, state and history
before retrying. There is no automatic write retry and missing audit rows do not
prove rollback. Ticket history intentionally retains its existing resolution prefix;
it should not be confused with the minimal central audit description.

## Listing and usability

The list supports 25/50/100 rows per page (default 25), bounded literal search,
status/category/priority/technician filters and an explicit Unassigned filter. Search
retains the original ticket/subject/description/name/Department/category/technician
coverage and adds Employee number. `%`, `_` and `!` are literal in the new HTTP
listing. Invalid filters fail clearly instead of silently widening results.

Filtered totals/status cards and the bounded page share a read-only REPEATABLE READ
snapshot. Counts describe the full matching set, not only the current page. Ordering
is creation timestamp then unique ticket ID descending; oversized pages clamp.
Navigation preserves every filter. Historical category/technician options are read
filters and never grant assignment eligibility.

## Remaining limits

- Separate pages can shift during concurrent writes. Production-scale count/search,
  OFFSET and reference-selector performance remains unverified. Reports and a
  ticket's history reader retain their existing unbounded behavior.
- There is no optimistic assignment token: a stale assignment form can replace a
  newer assignment while the ticket is still assignable. State transitions are
  checked under locks; this does not guarantee absence of deadlocks.
- Legacy/direct SQL writers can bypass validation, locks, history and central audit
  conventions. Coordinate compatible writers and privileged DDL maintenance. Metadata
  checks do not fence external schema changes.
- Two similar submissions can create two valid tickets. Uncertain commits require
  inspection before retry; there is no exactly-once submission contract.
- Compatible UTF-8 storage and staging/load/deployment checks require operator
  review. No company database has been inspected or deployed by this task.

## Verification

```powershell
python -m unittest discover -s tests -p test_help_desk.py -v
python -B tests/mysql_helpdesk_smoke.py --mysqld "PATH_TO_MYSQLD"
python -B tests/mysql_helpdesk_browser.py --mysqld "PATH_TO_MYSQLD"
python -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
python -B scripts/ci_checks.py python
python -B scripts/ci_checks.py javascript
python -B scripts/ci_checks.py mysql
python -m pip check
```

The new smoke suite is discovered by existing CI and uses only verified fresh
loopback servers with synthetic data. It exercises real lock waits, racing workflow
requests, rollback, uncertain commits, history/audit isolation, history preservation,
storage rejection, filters and permissions. The native Chrome wrapper composes the
existing security/IT authorization runner and verifies persisted ticket/history/audit
results after native form use. Browser tests remain local-only. Infrastructure and
application failures must be distinguished and reported; successful tests do not
authorize company deployment.
