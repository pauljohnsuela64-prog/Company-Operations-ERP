# Leave Management reliability

This change preserves the existing Leave permissions, CSRF/session protection,
schema compatibility gate, calendar-day calculations and pending-only workflows.
It adds no migration, entitlement amount, statutory rule, deduction, approval role,
Payroll integration or employment lifecycle publication. Company deployment is a
separate approval.

## Existing approval implementation

The previous repository defined `approve_leave_request` twice. Python bound the
later definition, which included yearly entitlement checks; the earlier definition
was unreachable and omitted those checks. There is now one implementation retaining
the effective rules:

- Count inclusive calendar days, including weekends and holidays as before.
- For each touched calendar year, compare overlapping approved days for the same
  Employee/type with that type's existing annual entitlement. NULL remains unlimited.
- Approve, reject and cancel only PENDING requests. Approved requests cannot be
  cancelled through this workflow. Rejected/cancelled requests release their dates
  for a new request.
- Reject approval when any covered Attendance row is not ON_LEAVE. Keep existing
  ON_LEAVE rows and their notes; insert missing ON_LEAVE rows and approve the request
  in the same transaction. Cancellation/rejection create no Attendance rows.
- Existing inactive types can still be approved for previously submitted requests.
  New requests require an active type. No Employee employment-status rule is added.

No existing entitlement or historical record is changed. Existing balance/report/
Excel export readers retain their calculations and formula-injection protection.

## Validation and transactions

Request/actor IDs must be positive signed INT values. Dates use strict YYYY-MM-DD
and MySQL's years 1000 through 9999. End cannot precede start. Reasons and rejection
reasons are required, valid UTF-8 text of at most 500 characters; unsupported control
characters and duplicate submitted fields are rejected. Invalid values remain in
escaped forms for correction, including unavailable Employee/type selections.
Browsers can display invalid dates/numbers as blank in native input controls.

The existing DECIMAL(5,2) total-days column can store at most 999 inclusive whole
calendar days. Longer new requests are rejected before SQL rather than truncated
under non-strict SQL mode. This is a storage restriction, not a new leave allowance.
Stored malformed/oversized ranges cannot be approved automatically and need operator
review. Maximum-date approval avoids incrementing beyond 9999-12-31.

Leave Type forms retain saved/submitted values. Existing code/name/description
limits are enforced at both the HTTP and repository boundaries, including code
uppercasing expansion. Entitlements remain optional, nonnegative DECIMAL(5,2)
values, with at most two decimal places; NaN, Infinity, overflow and implicit
rounding are rejected. This does not change configured entitlements or calculations.

Creation locks the Employee first, checks the selected type inside the transaction,
then performs a current locking overlap read for PENDING/APPROVED requests across
all types. Approval takes the same Employee lock before reading balances and writing
Attendance. This serializes cooperating requests even when no overlapping row exists
yet. Pending-state locks protect competing approve/reject/cancel operations. Existing
legacy overlapping rows are not repaired; approval retains the prior treatment of
existing ON_LEAVE attendance rather than introducing a retrospective overlap policy.

Writes explicitly start a transaction, verify required InnoDB tables, commit once,
and roll back on failure. Approval also verifies Attendance's existing full unique
Employee/date index. Capability checks only inspect metadata; they never repair
schemas. Type/number duplicates and lock/FK conflicts return useful errors rather
than raw connector details. HTTP 400 means invalid input, 404 missing target, 409
conflict, and 503 incompatible storage or an unconfirmed save. Successful operations
keep their existing redirects. Repeated transitions now explicitly return 409.

A lost COMMIT acknowledgment or postcommit cleanup failure can leave a committed
operation while returning 503. Reload and inspect request status, number and
Attendance before retrying. There is no automatic retry or guarantee of rollback
from an exception. Central auditing remains best effort after successful repository
return: APPROVE, REJECT and CANCEL keep their existing identifiers/descriptions and
fallback lookup behavior. CREATE and Leave Type operations still do not add central
business audit events. Private reasons are excluded from audit descriptions.

## Listing

The request list supports 25, 50 or 100 rows per page (default 25), bounded literal
search, status/type/Department filters and an inclusive overlapping-date range.
Search covers request number, Employee number/name and type name, not private
reasons. `%`, `_` and `!` are literal search characters. Inactive types and
Departments remain available for historical filters.

Filtered total/status counts and the bounded page share a read-only REPEATABLE READ
snapshot. Counts describe all matching requests. Ordering is creation timestamp then
unique request ID descending; out-of-range pages clamp. Navigation retains filters.
Department filtering uses the Employee's current assignment, as the schema has no
historical Department snapshot. No history is rewritten.

## Limits and deployment

- Pagination can shift between requests during concurrent writes. Large OFFSET,
  count/search scans and full Employee/type selectors need production-scale staging
  measurement. No indexes or migrations are added here.
- Type edits/status toggles have no optimistic revision token; stale forms may
  overwrite a newer type edit. Request status transitions are checked under locks.
- Legacy workers and direct SQL can bypass the Employee locking/validation
  conventions. Coordinate compatible writers and schema maintenance; application
  metadata checks do not fence concurrent privileged DDL.
- Existing manual Attendance edits can later change Attendance associated with
  approved Leave. Reconciliation/ownership policy requires separate HR approval.
- Audit delivery is not durable/exactly once. Missing audit rows do not prove that a
  business operation rolled back.
- No company database or production performance has been verified. Successful
  development tests are not deployment authorization.

## Verification commands

```powershell
python -m unittest discover -s tests -p test_leave.py -v
python -B tests/mysql_leave_smoke.py --mysqld "PATH_TO_MYSQLD"
python -B tests/mysql_leave_browser.py --mysqld "PATH_TO_MYSQLD"
python -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
python -B scripts/ci_checks.py python
python -B scripts/ci_checks.py javascript
python -B scripts/ci_checks.py mysql
python -m pip check
```

The MySQL suite uses a verified fresh temporary server, synthetic records and actual
transactions. It covers concurrency, rollback/uncertain commits, Attendance/balance
compatibility, history, security and storage rejection. The Chrome wrapper uses the
existing isolated security-review runner and checks persisted results after native
forms. Browser execution remains local-only; environmental DevTools/shutdown failures
must be reported separately from application assertions, never silently skipped.
