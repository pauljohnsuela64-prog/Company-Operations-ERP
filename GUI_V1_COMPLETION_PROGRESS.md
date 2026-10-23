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
