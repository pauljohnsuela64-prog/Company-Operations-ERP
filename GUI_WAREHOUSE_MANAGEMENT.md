# GUI Phase 3B-2: Warehouse Management

Based on verified origin/main abd540b7d1d500db74e35bc2ee99f0e1d7ecbabd.
Only the three Warehouse templates change application presentation. Existing
workspace macros and CSS are reused unchanged; no dependencies are added.

- Workspace page headers, labeled search/status/page-size controls, results,
  active/inactive badges, action groups and filter-preserving pagination.
- Separate initial-empty, filtered-empty and unavailable states. Failed reads
  show unavailable results without a misleading count or pagination.
- Captioned table with scoped headings, wrapping long names/locations and a
  named, focusable horizontal scroll region. The existing category-table layout
  supplies the same five-column dimensions without adding shared CSS.
- Add/Edit panels use the established two-column grid, full-width optional
  location and responsive Save/Cancel actions. All labels reference inputs;
  required markers accompany the existing native required attributes.

All field names/types/limits, request.form fallbacks, values, routes, methods,
CSRF fields, explicit status targets and confirmation text are retained.
Manager permission checks remain in the templates; readers receive no write
controls. Eligibility, receiving, stock, history, transactions, auditing and
backend policies remain unchanged. No company database was used.

## Verification

- Initial Warehouse unit suite: 14 passed.
- Disposable MySQL Warehouse suite passed: pagination/filter safety, rollback,
  concurrency, stock locks, historical preservation and receiving eligibility.
- Added contract tests: 3 passed, including 48 comparisons against the verified
  parent for forms, roles, status targets, values, confirmations and page URLs.
- Full Python suite, run once after implementation: 519 passed. Expected fault
  injection logs include blocked database access and simulated cleanup failures.
- JavaScript/navigation: 11 passed. Python/Jinja and JavaScript syntax,
  dependency consistency and whitespace checks passed; new test sources were
  also checked explicitly because the CI syntax helper selects tracked files.
- Combined original Warehouse workflow, security and new visual Chrome suite
  passed on a verified disposable MySQL/HTTP server. Manager and read-only views
  covered 1440, 1024, 768, 390 and 320px, long populated tables, filtered empty
  results, injected unavailable reads, Add/Edit forms and retained validation.
  Checks covered 25/50/100 pages, status badges/targets, confirmation cancellation
  and submission, CSRF denial, reader denial, escaping, labels, keyboard table
  scrolling, field/filter overlap and page-wide overflow. No captured console
  errors or uncaught JavaScript exceptions. Representative screenshots were
  visually reviewed at all four requested widths.
- Synthetic history/stock/movement/PO snapshots remained unchanged, with exactly
  the expected committed Warehouse audits. Disposable servers stopped and their
  temporary database directories were removed.

The initial sandboxed Chrome attempts failed before browser assertions with a
local CDP connection reset; the same isolated suite passed outside the sandbox.
No browser security flags or isolation/cleanup guards were weakened. The runner
composes the existing security fixture (including its existing synthetic grants)
and original Warehouse browser tests without changing either.

Run tests/mysql_gui_warehouse_browser.py with ERP_GUI_BOOTSTRAP_CSS pointing to
an existing Bootstrap 5.3.8 stylesheet and ERP_GUI_SCREENSHOTS to a temporary
artifact directory. Bootstrap is served locally through CDP; other external
browser resources are blocked. Artifacts and database files are not committed.

Physical devices, screen readers and production capacity remain unverified.
Tables intentionally scroll within their containers on narrow screens.
