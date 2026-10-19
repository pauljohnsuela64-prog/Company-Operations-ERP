# Employee & HR Step 4A: server-side listing

Starting checkpoint: `5cc28c6`, branch `fix/hr-employee-reliability`.

`GET /employees` retains `employees.view` and the existing fresh authorization,
disabled-account checks and create/edit button permissions. Every Employee remains
visible to an authorized viewer, as before; there is no new status/Department
restriction, public API, export, permission, role grant or migration. Search covers
only Employee number and displayed first/middle/last names. Email, phone, lifecycle
evidence and other confidential fields are not added as search targets.

Search trims surrounding whitespace, accepts up to 100 Unicode characters and
rejects invalid Unicode/internal ASCII control characters. Empty/whitespace-only
search shows the bounded default listing. Each field is matched by **literal
prefix**, not arbitrary substring: `Ann` matches a first name starting with Ann.
`%`, `_` and `!` are escaped using explicit SQL `ESCAPE '!'`; only the application
adds the trailing wildcard. Punctuation and SQL-looking strings remain bound data.
There is no implicit full-name tokenization or advanced filtering.

Comparisons and ordering use each column's existing MySQL collation, with no forced
case folding. Disposable tests verify case/accent-insensitive utf8mb4_0900_ai_ci and
case-sensitive utf8mb4_bin behavior. Deployment collation may differ; this change
does not alter it. Jinja escapes search values, results and navigation URLs.

`employee_listing.py` validates inputs before connecting: page defaults to 1 and
must be 1–2,147,483,647; page size defaults to 25 and must be 1–100. The UI offers
25/50/100 and preserves any other valid selected size. Duplicate supported query
parameters, malformed/empty numbers, zero, negatives and oversized numbers return
400 with a visible error and no listing query/count. Errors do not display invented
result totals. Valid out-of-range pages clamp to the last available page; an empty
result has page 1 of 1. Unknown query keys have no effect.

`get_employee_page()` uses one dedicated READ ONLY / REPEATABLE READ snapshot for
the filtered COUNT and paginated SELECT. Both share the exact Employee predicate.
The data query fetches only display fields and Employee identity, joins Department
display fields, orders by last name, first name and unique Employee ID, and applies
parameterized LIMIT/OFFSET. The snapshot ends with rollback/close and never commits
business writes. Future visibility rules must be added to both queries together.

The existing shared `get_all_employees()` remains unchanged for other module
selectors. Employee/Department write repositories, revisions, lifecycle flags and
history, Attendance/Leave, account activation, IT custody and Payroll are unchanged.
Existing global CSRF protections remain intact; the listing is a read-only GET.

Previous/Next links preserve search and page size. Search submission omits page,
resetting to the first page, and Clear returns to defaults. Existing Bootstrap grid
classes let the form wrap; the existing responsive table container is preserved.
Create/Edit actions retain their original permission checks.

## Performance and pagination limits

The inspected existing Employee indexes cover primary identity, unique Employee
number/email and Department FK. No name/sort index was added. Prefix conditions
avoid user-provided broad LIKE wildcards, but OR conditions over unindexed names,
filtered counts and name sorting can still scan/sort substantial data. Default
listing intentionally counts all visible Employees while fetching only one page.
Deep OFFSET pagination can remain expensive. Stable tie-breaking prevents ambiguity
on an unchanged dataset; separate HTTP pages do not share a snapshot, so concurrent
name edits/inserts/deletions can move rows between pages. A frozen export/keyset
contract is outside this checkpoint.

An initial disposable local run at 67/1,000/5,000 rows measured approximately
8/11/14 ms for one connection + filtered count + page query, with at most 25 rows
returned. These single samples are not production capacity, latency guarantees or
representative concurrency benchmarks. Larger deployments need measured query plans
and a separately reviewed indexing proposal.

## Verification

`test_employee_listing.py` covers parameter boundaries, matching count/data
predicates, bound SQL, transaction cleanup, escaping, navigation, view-only buttons,
permission revocation and disabled-account rejection. `mysql_employee_listing_smoke.py`
uses fresh isolated MySQL and synthetic records to verify literal patterns, Unicode,
punctuation, collation behavior, injection payloads, stable tied-name ordering,
first/middle/last pages, filtered counts, concurrent reads and unchanged rows in
strict/non-strict modes. It also measures small synthetic datasets.

`mysql_employee_listing_browser.py` composes native listing tests with existing HR
Add/Edit, revision, security and IT authorization browser workflows. It creates only
disposable records and verifies listing fixture rows remain unchanged. External CDN
assets are blocked by the existing browser harness, so fully styled desktop/mobile
appearance still needs manual inspection with the normal approved assets available.

Manual review: check styled desktop/mobile form wrapping and table scrolling; search
and clear, back/forward navigation, retained page size/query, empty results and
visible validation errors; confirm viewer/manager action visibility and unchanged
Employee Add/Edit workflows. Lifecycle publication and Payroll remain paused.
