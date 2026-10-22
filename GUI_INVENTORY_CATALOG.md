# GUI Phase 3B-1: Inventory Categories and Items

Based on main e567560e052eeafe0f39b2a3f7bf19f669b49791. Six catalog
templates adopt the existing navy/slate workspace foundation. No backend,
schema, dependency, permission, calculation, transaction or auditing code changes.

## Presentation

- Shared page headers, active/inactive badges, results, empty/error states,
  pagination and Save/Cancel actions reuse workspace_components.html unchanged.
- Filter controls retain their labels, names, options, values and GET routes.
  Items retain their additional category filter; its desktop layout accommodates
  all five filter groups and stacks at existing tablet/mobile breakpoints.
- White form panels, required indicators and associated labels reuse the existing
  form grid. Desktop fields align in two columns; mobile fields and actions stack.
- Tables have captions, scoped column headings and named, keyboard-focusable
  scroll regions. Long codes, names and descriptions wrap inside cells. Actions
  remain in the scroll region, preserving every column on narrow screens.
- Empty results remain distinct from failed reads; unavailable results do not
  display a false zero count. No client sorting/filtering or additional scripts.

## Preserved contracts and policies

All routes, GET/POST names, methods, field types/limits/requiredness, CSRF fields,
explicit activation/deactivation targets and confirmation messages are retained.
Permission checks remain with the caller. Read-only users receive no write actions.
Category selection retains inactive historical and unlisted submitted selections.
Item creation retains the six existing UOM options and invalid submitted values;
editing retains its text UOM field. Decimal reorder handling is unchanged.

Changing a UOM still performs no unit conversion or historical quantity rewrite.
The historical UOM policy remains a separate business decision. Category/item
eligibility, stock calculations, Procurement, rollback, audit, lock and uncertain
commit behavior are unchanged. Payroll and paused HR Lifecycle policies are untouched.

## Verification

- Focused Category and Item unit tests: 12 + 13 passed.
- Full Python suite: 516 passed, run once after implementation.
- JavaScript navigation: 11 passed.
- Syntax: 164 Python sources, 110 Jinja templates and 25 JavaScript files passed;
  dependency consistency and whitespace checks passed.
- Disposable MySQL Category and Item suites passed, including concurrency,
  rollback/audit failure behavior, historical category retention, UOM edits,
  stock/history preservation, permission refresh and CSRF.
- A read-only render comparison against main passed 48 form/field/option/action,
  confirmation and pagination cases across all six templates, manager/reader,
  populated/unavailable results and original/submitted values.
- Combined Chrome security, original Category/Item workflow and new visual suites
  passed. Manager and read-only accounts covered both modules at 1440, 1024,
  768, 390 and 320px. Populated, long, empty and unavailable results; filters;
  25/50/100 pagination; native confirmations/status actions; retained validation;
  duplicate/no-op submissions; escaping; permissions and CSRF were exercised.
- Representative screenshots were reviewed across all five widths, including
  mobile forms, tablet edits, long tables and read-only/empty/error states.
  No page-wide overflow, overlapping form/filter groups, missing labels, duplicate
  IDs or captured JavaScript exceptions/console errors were found. Scroll regions
  support keyboard scrolling and visible focus.
- Fixture history, stock, movement and PO snapshots remained unchanged. Committed
  test record audits matched the expected actions exactly. Disposable processes
  exited and temporary database directories were removed.

The browser runner composes the existing isolated security setup; unrelated IT
browser workflows remain in their separate tests. Existing Bootstrap 5.3.8 CSS
is supplied locally through CDP; other external browser requests are blocked.
No Chrome security flags, server identity guards or cleanup safeguards are weakened.
Only synthetic roles receive existing permission codes inside the disposable DB.
Test-only outage injection never changes application routes or company data.

Run tests/mysql_gui_inventory_catalog_browser.py with ERP_GUI_BOOTSTRAP_CSS
pointing to that existing stylesheet and ERP_GUI_SCREENSHOTS to a temporary
artifact directory. Screenshots and database data are not committed.

## Outstanding validation

Physical devices, screen readers and production capacity remain unverified.
Existing list-query performance, category lookup size and UOM history limitations
are unchanged. Wide tables intentionally scroll within their containers.

Post-merge main CI run 39789570258 was still running at review: Python and
JavaScript jobs passed; disposable MySQL integration remained in progress. No
failure had been reported. Its final result must be checked before publication;
this local implementation does not change the CI harness.
