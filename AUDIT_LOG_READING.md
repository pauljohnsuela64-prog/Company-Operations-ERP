# Audit Logs reading contract

`/admin/audit-logs` remains an authenticated, `audit_logs.view`-protected, read-only
GET page. Existing authentication, CSRF and global schema compatibility checks
remain in place. There are no event editing/deleting, retention, export, cleanup,
permission, schema or business-writer changes in this feature.

## Filters and pagination

The page accepts `search`, `module`, `action`, `start_date`, `end_date`, `page`
and `page_size`. Page size is 25 (default), 50 or 100; page must be a positive
ASCII integer through 2147483647. Pages beyond the last are clamped. Links retain
all filters and page size; submitting the filter form returns to the first page.
Counts include every matching historical row, including rows whose actor ID is
NULL. Ordering is `created_at DESC, audit_log_id DESC`, with the unique ID breaking
timestamp ties. Empty database, empty filtered result and failed load states
are distinct; failed reads do not masquerade as zero matches.

Search is limited to 100 Unicode characters and module/action to 50. Text is
trimmed; controls and invalid Unicode are rejected. Module/action values retain
case and historical naming conventions. Unknown valid values remain bound equality
filters and return no matches if absent, rather than reverting to All. MySQL's
existing column collation determines case/accent comparison; this change does not
redefine it. Search uses the original username/module/action/entity/description
fields. `%`, `_` and the escape character `!` are literal search characters;
all values, limits and offsets are bound parameters.

Dates must be valid YYYY-MM-DD dates in years 1000-9999, with start <= end. Both
calendar days are inclusive in the existing MySQL session time zone; no historical
timestamps are rewritten or reinterpreted. Missing dates are optional. Invalid,
duplicate or unsupported query keys return HTTP 400 without running a broader
query. Read/storage failures return generic 503 responses without SQL details.

## Read consistency and compatibility

The repository's `get_audit_log_page(filters, include_options=True)` returns rows,
full filtered total, page bounds, normalized filters and distinct module/action
options in one InnoDB REPEATABLE READ, READ ONLY consistent snapshot. It rolls back
the read transaction, closes resources and never commits or writes audit history.
It requires the existing InnoDB audit table with a full single-column primary key
on `audit_log_id`; unsupported/missing storage fails without automatic repair.
The global schema gate still controls database access. No migration is added.

`get_filtered_audit_logs(...)` remains a list-returning compatibility API but now
returns at most `page_size` rows (25 by default, never more than 100). Callers
needing older rows must request pages or use the page API and total. The previous
implicit latest-500 list contract is intentionally replaced. The separate legacy
filter-options helper and all audit writers are unchanged.

## Privacy and limitations

Descriptions, actors and targets use normal Jinja escaping and the existing
permission boundary; no new fields or export are exposed. Page responses use
`Cache-Control: no-store` (normalized by the existing HTML/CSRF middleware) and
`Referrer-Policy: no-referrer`. Do not put
credentials or private details in search URLs: browser history, server/proxy logs
and authorized viewers can still retain them. Existing descriptions are not
redacted or rewritten by this feature; business writers remain responsible for
avoiding sensitive content. Audit delivery remains best effort, with no durability,
exactly-once or tamper-proof guarantee.

A snapshot makes one response consistent, not an entire multi-page browsing
session. Concurrent inserts/updates can shift offset pages on subsequent requests.
Counts, leading-wildcard search, distinct filter options and deep offsets may be
expensive; production performance and large option sets remain unverified. This
change does not add indexes, external-writer controls or a retention policy.
Schema changes still require a controlled, separately authorized deployment.

## Verification

Commands and coverage are in [tests/README.md](tests/README.md). Use only the
verified disposable MySQL launchers and synthetic fixtures. Development tests
never authorize a real company database migration or production deployment.
