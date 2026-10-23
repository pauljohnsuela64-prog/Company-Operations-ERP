# GUI v1 completion progress

Baseline: origin/main 8d2a8367515d8b60152e38c280b5a5a525a72c52.
Warehouse PR #28 merged and its seven-file tree verified present before branching.
Branch: feat/gui-v1-remaining-modules. Local commits only; no publication.

## Status

- Previous Foundation, Procurement, Inventory Catalog and Warehouse phases: preserved.
- 3B-3 Stock: in progress; reviewing quantity/idempotency/report contracts.
- 3C Finance: pending.
- 3D HR / Attendance / Leave / current-mainline Payroll: pending.
- 3E IT Assets / Help Desk: pending.
- 3F Administration / authentication / recovery: pending.
- Phase 4 cross-application polish and final regression: pending.

## Verification policy

Only verified disposable MySQL and synthetic fixtures. No company DB, migrations,
policy changes, seeded grant changes or paused-branch merges. Reuse successful
checks unless later edits invalidate them. Document actual Chrome coverage and
limitations. Each verified workstream receives a separate local commit.

No implementation commits yet. No known blocking defect. Next: Stock Management.

## 3B-3 Stock — verified, ready for local commit

Files: all seven templates in templates/inventory/stock/; static/css/style.css
(scoped opt-in rules); tests/gui_contracts.py, mysql_gui_contracts.py,
mysql_gui_v1_browser.py, browser_gui_v1.cjs; this progress document.

Reused workspace header macros, cards, typography, action groups and scroll
regions. Added associated labels and required markers without changing field
constraints, values, submission UUIDs or CSRF. All report fields and links remain.
No backend change. Existing read-only reconciliation cautions remain verbatim.

Tests: 11 stock + 6 reporting Python tests; disposable mysql_stock_smoke and
mysql_inventory_reporting_smoke passed after implementation with baseline
contract checks for all five full-page templates. Syntax and whitespace passed.
Chrome manager/reader at 1440/1024/768/390/320 passed native route checks,
empty/invalid report filters, long text, hidden write controls, retained invalid
quantity and submission ID; baseline login/session/CSRF workflows also passed.
Representative screenshots reviewed at 1440, 768, 390 and 320. No page overflow,
control overlap, missing labels, duplicate IDs or captured JS errors.
A new runner's unread-result check failed after Chrome assertions; corrected
its cursor consumption and reran successfully. No application regression found.

The contract helper requires the baseline Git object above to be available;
it runs only when explicitly invoked against disposable suites, not during
normal unittest discovery. No company database connections are opened by it.

Remaining: Finance, HR/Payroll, IT/Help Desk, Admin/auth, final cross-module
polish/regression. No blocker. Next workstream: Finance.

## 3C Finance — verified, ready for local commit

Previous Stock commit: ff9ace3. Finance files: templates/finance/index.html,
expenses/{index,add,edit,view}.html, budgets/{index,add,edit,view}.html,
reports/index.html; scoped shared CSS, browser fixture/routes and this checkpoint.
Expense Categories and the selection/report partials remain intact.

Workspace cards/headers, associated labels, named keyboard-scrollable tables,
readable currency cells, responsive filters, badges and Budget pagination.
Existing formulas, exact formatting, options, historical selections and every
form/link/script contract preserved. Screenshot review caught currency wrapping
and inconsistent Budget header utilities; presentation corrected and rechecked.

Verification: 30 Finance + 15 Budget Python tests passed. Disposable validation,
Budget Management, reporting, payment and audit suites passed. Baseline contracts
checked wherever those suites render templates; the payment suite renders none,
so the wrapper correctly reported no template coverage after its DB assertions
passed (not an application failure). Existing Finance/Budget Chrome functional
suite passed, including retained corrections, exact paid/budget labels, exports,
historical pagination, CSRF and persisted audit checks. New native-route visual
checks and baseline contracts passed for all ten Finance pages, manager/reader,
1440/1024/768/390/320. Representative screenshots reviewed at all requested
classes of width. Syntax/whitespace passed; no JS errors or page overflow.

Remaining: HR/Payroll, IT/Help Desk, Admin/auth, final polish/regression.
No significant blocker. Next: mainline HR, Attendance, Leave and Payroll GUI.

## 3D HR / Attendance / Leave / Payroll — verified, ready for local commit

Previous Finance commit: 67ebfdc. Files: Departments and Employees full pages;
Attendance form/index (Add/Edit inherit form); all Leave pages; all mainline
Payroll templates; HR conflict; reusable browser routes/fixtures; this checkpoint.

Workspace styling and hierarchy, associated labels, scroll regions, currency
cells, badges and recovery presentation. Added the missing Leave Requests page
heading and rejection-reason label. Preserved original input constraints,
revision tokens, historical options, approval controls and confidential values.
No paused branch merged. No payroll calculations/policies changed.

82 targeted Python tests passed (33 HR, 6 employee listing, 19 Attendance,
24 Leave). Six disposable suites passed: HR validation, HR revision, HR audit,
employee listing, Attendance, Leave; baseline template contracts passed for
rendered pages. Original HR, Attendance and Leave Chrome workflows passed with
native corrections, stale-tab conflicts, calendar/status/approval behavior,
exports, historical pagination, fresh permission denial and CSRF. The existing
audit smoke suite's Payroll submit/return/approve/pay and unauthorized/concurrent
actions passed; its wrapper correctly reported no Payroll template coverage.

New visual suite passed all 26 native HR/Payroll routes at
1440/1024/768/390/320 with manager, reader and applicable approver roles.
Baseline form/link/script comparisons passed for all these routes, including
paid payslips. Snapshot checks proved all stock, employee, department, attendance,
leave, compensation, payroll, expense and budget fixture records unchanged.
Unpaid payslips still redirect to the entry page. Screenshots reviewed across
all four width classes. No page overflow, duplicate IDs, missing labels,
overlapping filter/action groups or captured JavaScript errors.

Fixture-only failures were resolved: missing required generated_by, occupied
user ID, missing adjustments table in the base security fixture and a draft
period used for a paid-only payslip. Existing schema was loaded only in the
disposable fixture, and separate draft/paid records now test both paths.

Low severity baseline presentation observation: Payroll period entry rows have
two identical View links in separate cells, but one Actions header (present
before this branch). No behavioral/security blocker; address as a narrowly
reviewed presentation correction during Phase 4, preserving the entry endpoint.

Remaining: IT/Help Desk (implementation and verification underway independently),
Admin/auth, final polish/regression. Next: finish IT/Help Desk.

## 3E IT Assets / Help Desk — verified, ready for local commit

Previous HR/Payroll commit: b60b128. Files: all 9 full IT Asset pages and
4 Help Desk pages; reusable browser fixture/routes; this checkpoint.

Corporate workspace headers/cards, accessible labels (including unique per-row
maintenance completion dates), badges, named scroll regions and report forms.
Existing lifecycle, assignment/return tokens, historical categories, maintenance,
technician eligibility and ticket-state forms remain unchanged.

65 targeted Python tests passed (37 IT, 28 Help Desk). All seven disposable
suites passed: IT authorization, asset validation, category validation, lifecycle,
reporting, audit and Help Desk. Baseline form/link/script comparisons passed.
The original Help Desk + composed IT browser workflows passed: all 17 management
route denials/CSRF checks, lifecycle recovery and maintenance, report exports,
revocation, Help Desk create/assign/start/resolve/close, pagination and historical
snapshots/audits. New visual suite passed manager/reader across 15 native routes
at 1440/1024/768/390/320, including open maintenance and in-progress tickets.
Business snapshots unchanged; no browser JS errors, page overflow, missing
labels, duplicate IDs or filter/action overlaps. Representative screenshots
reviewed at desktop/tablet/mobile. Syntax and whitespace passed.

Remaining: Admin/auth (independent presentation work underway), Phase 4
cross-module polish and final regression. No blocker. Next: Admin/auth.

## 3F Administration / authentication / recovery — verified, ready for commit

Previous IT/Help Desk commit: 8aaaf86. Files: seven Admin templates, login,
CSRF error and logout; scoped auth CSS; browser routes/checks; this checkpoint.

Workspace users/roles/audit tables and forms, unique associated per-user role
labels, navy/slate login with main landmark and accessible errors, styled
explicit logout and CSRF recovery. Password handling, required/autofocus fields,
permissions, self/last-admin safeguards, tokens, retries and POST actions remain.

70 targeted Python tests passed: Admin 5, Audit Logs 21, security 44. Disposable
Admin integrity, Audit Log reading and session/CSRF security suites passed.
Original Admin and Audit Log Chrome suites passed with exact changed-account
audits, original memberships/passwords/history preserved, last-admin/self
controls, read-only audit traversal and permission/CSRF denials. All rendered
baseline control/link/script contracts passed. New native layout checks passed
manager/audit-reader at 1440/1024/768/390/320, plus anonymous login, invalid
credentials, safe GET logout and invalid-token recovery screenshots at every
width. Reviewed desktop login, tablet users, mobile login/errors/recovery.
No captured JS errors, page overflow, label/ID issues or control overlap.
Syntax/whitespace passed. No security policy or production grant changes.

Remaining: Phase 4 polish, combined visual checks, final Python/JS regression,
final report and diff audit. No blocker. Next: Phase 4.
