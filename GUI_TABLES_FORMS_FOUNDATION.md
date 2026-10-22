# GUI Phase 2: Tables, filters and forms

This phase modernizes only Suppliers and Expense Categories. The shared shell,
dashboard, navigation controller, routes, repositories, validation, permissions,
auditing and database contracts are unchanged. No application JavaScript or new
external dependency is introduced. Bootstrap 5.3.8 remains the existing framework.

## Reusable presentation

`partials/workspace_components.html` provides `page_header`, `filters`, `badge`,
`result_header`, `pages`, `empty_state`, `field` and `form_actions` macros. Callers
retain responsibility for destination permissions and server-created pagination
URLs. Dynamic text and field values retain Jinja autoescaping; no safe filter or
client-rendered HTML is introduced. Scoped workspace classes use the Phase 1
colors, spacing, radii and elevations. Other module interiors are not migrated.

Both lists share labeled GET filter controls, result counts, semantic tables,
text-and-dot status badges, action groups and responsive pagination. Column and
row headers have explicit scope. A named, keyboard-focusable region contains
horizontal table overflow and has a visible focus outline. Long text wraps rather
than being silently truncated. The region has no vertical height limit; vertical
scrolling stays with the page. Empty tables drop their minimum width and hide
unused column headings so empty/error text is readable at narrow widths.

Add/Edit forms use labeled fields with unique IDs, a two-column desktop grid,
full-width textareas and shared Save/Cancel footers. Required indicators reflect
only existing required attributes. Supplier code/name remain required; contact,
email, phone and address remain optional. The browser email input and backend
email-validation difference are unchanged and belong to the later policy cleanup.
All field names, types, maxlength limits, default/retained values and POST methods
match main. Status forms retain CSRF and explicit is_active targets. Supplier
Activate/Deactivate confirmation prompts are preserved; categories keep their
existing direct action. No permission, eligibility or approval policy is changed.

## Verification

The full Python suite and navigation JavaScript tests run without configured DB
access. The Supplier and Expense Category disposable MySQL suites cover bounds,
create/edit/status/rollback, pagination/filter contracts, concurrency, auditing,
permission refresh, eligibility and preserved financial/PO history. An isolated
render comparison checks every Add/Edit field contract against main.

`tests/mysql_gui_tables_forms_browser.py` composes the existing cross-module
security runner, both existing module browser workflows, and the Phase 2 visual
matrix in `tests/browser_gui_tables_forms.cjs`. Use installed MySQL/Chrome with:

- `ERP_GUI_BOOTSTRAP_CSS`: a temporary copy of the existing Bootstrap 5.3.8 asset.
- `ERP_GUI_SCREENSHOTS`: a temporary screenshot artifact directory.
- `python -u -B tests/mysql_gui_tables_forms_browser.py`

Only the existing verified disposable server is used. Bootstrap is served over
CDP; other external browser requests are blocked and security flags are unchanged.
Synthetic read-only fixture grants are confined to this server. A test-only reader
patch raises the existing database exception on a special query parameter to test
the actual 503 route/template boundary; no production endpoint or flag is added.
Historical Supplier/Category rows, PO and Expense snapshots are checked unchanged.
The exact audit sequence includes the existing four workflow events plus two
native status changes; cancelled/failed/no-op/denied requests add no success audit.

The viewport matrix is 1440, 1024, 768, 390 and 320 CSS pixels with a 1000-pixel
viewport height. It covers manager and read-only users in both modules, populated
and long-text tables, empty and unavailable states, Add/Edit forms, native status
actions/confirm cancellation, retained validation errors, label associations,
keyboard table focus, contained scrolling and absence of page-wide overflow.
Screenshots are local artifacts and are not committed. Representative populated,
empty/unavailable, Add/Edit and validation-error screenshots were manually reviewed
at desktop, tablet and mobile widths. The narrow-screen form footer stacks its
buttons so long action labels remain readable rather than wrapping vertically.

Verification passed: 516 Python tests, 11 JavaScript navigation tests, both
module disposable MySQL suites and the combined Chrome security/workflow/visual
matrix. No page-wide overflow, overlapping fields/filters, console.error calls
or uncaught JavaScript exceptions were observed. Existing form contracts were
also compared against main by isolated rendering. Calculated text contrast meets
4.5:1 and Phase 2 control/focus borders meet 3:1; this is not an accessibility
certification. Python/Jinja/JavaScript syntax, dependency and whitespace checks
passed.

## CI and limits

Post-merge main run 39728956022 (580e66d) completed successfully, including the
Disposable MySQL job. The earlier recurring hosted startup issue is tracked
separately; this change does not claim a root-cause fix and does not change the
CI harness, startup timeouts or identity safeguards.

Physical-device and screen-reader testing, production capacity, representative
production-data usability and translated-text testing remain outstanding. Mobile
tables intentionally scroll horizontally to preserve all columns and actions.
Supplier required-field/email policy and all paused Payroll/HR Lifecycle work
remain outside this phase. No migration, production grant, company DB operation,
push, merge or deployment is part of this task.
