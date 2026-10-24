# ERP v1.0 portfolio screenshot plan

Status: **planned; no screenshots captured or approved in this documentation task**.
The plan is based on the actual route inventory, dashboard/navigation templates,
module views and the previously verified synthetic demo scope. It does not claim
that the current browser session or every live record was inspected.

## Capture boundary

Use only an explicitly verified `company_operations_erp_demo` target and its
dedicated runtime account. Never use the original company database, run migrations,
reseed records, bypass permissions or change business status to improve an image.

Previous Chrome/CDP attempts were unreliable. A normal login also updates login
metadata, and viewing a form can update session state. The current task forbids
database changes, so authenticated capture is deferred. A later capture session
needs authorization for normal login metadata writes or a separately approved
disposable synthetic capture environment. Do not fabricate UI images or render
invented records as if they came from the working application.

## Visual format

- Primary set: PNG, 1440 x 1000 browser viewport, device scale factor 1, 100% zoom.
- Optional responsive set: 390 x 844, named separately from desktop images.
- Capture the page viewport without browser chrome, address bar, developer tools,
  terminal windows, tooltips, notifications or local file paths.
- Keep the native navy/slate design, consistent page header and navigation.
  Use one browser/theme and the same image dimensions throughout the desktop set.
- Wait for the pinned Bootstrap CSS, custom CSS, icons, fonts and table content
  to finish rendering. If CSS cannot load reliably, stop instead of publishing an
  unstyled page or fetching an unreviewed replacement asset.
- Use normal filters/pagination to frame a readable view. Do not edit page DOM,
  monetary values, counts, dates or workflow status for presentation.
- Capture useful detail without shrinking text to fit an entire long page.
  Separate detail images can supplement a module overview.

## Planned views

Filenames below are proposed names, not links to existing assets. Add images under
`docs/screenshots/` only after inspection; add README image references only once
those files exist and have passed review.

| Shot / proposed file | Actual page | Suggested role | Composition and acceptance check |
| --- | --- | --- | --- |
| 01 `01-dashboard.png` | `/dashboard` | Super Admin | Show the Operations Dashboard and workforce, operations/finance and IT/Payroll groups. Current-date counters may legitimately be zero; retain them. |
| 02 `02-human-resources.png` | `/employees` | HR Manager | Show fictional employee numbers, names, departments and employment states with readable table controls. Exclude unnecessary contact details. |
| 03 `03-attendance.png` | `/attendance` | HR Manager | Filter to the synthetic attendance date range. Show status and date filters; do not manufacture present-day attendance. |
| 04 `04-leave.png` | `/leave/requests` | HR Manager | Show the fictional approved leave request and the existing status/filter presentation. Do not approve or submit another request for the image. |
| 05 `05-payroll.png` | `/payroll/periods`, then an existing period detail | Finance Manager | Show the synthetic period and calculated entries. Label the caption as a calculation demonstration, not a paid Payroll run or certified salary result. |
| 06 `06-inventory.png` | `/inventory/stock` | Inventory Manager | Show item/warehouse balances and existing filters. Reconcile visible values with the existing movement history before publication; do not alter balances. |
| 07 `07-warehouse.png` | `/inventory/warehouses` | Inventory Manager | Show the fictional warehouse and its normal action/active-state presentation. Avoid submitting any status or edit form. |
| 08 `08-procurement.png` | `/procurement/orders`, then an existing order detail | Procurement Manager | Show supplier, order lines and the existing partial-receiving state. Leave the order unchanged. |
| 09 `09-goods-receipt.png` | `/procurement/receipts/history`, then an existing receipt detail | Procurement Manager | Show the existing receipt and quantities as evidence of the purchasing-to-stock workflow. Do not open a POST workflow or receive another delivery. |
| 10 `10-finance.png` | `/finance/expenses` | Finance Manager | Show the synthetic paid expense and clear amount/status columns. Caption as fictional financial data. |
| 11 `11-budget.png` | `/finance/budgets` | Finance Manager | Show the existing synthetic annual department budget and the supported budget presentation. Use the correct year filter. |
| 12 `12-administration.png` | `/admin/users` or `/admin/roles` | Super Admin | Show demo usernames, role names and active status. Never open password/reset dialogs, display generated credentials or change a grant. |
| 13 `13-it-assets.png` | `/it/assets` | IT Manager | Capture the genuine list or empty state. If no sample assets exist, either label the empty state honestly or defer the image to a separately approved data preparation task. |
| 14 `14-help-desk.png` | `/it/help-desk` | IT Manager | Show genuine ticket rows or the actual empty state. Do not create tickets or invent lifecycle history. |
| 15 `15-audit-logging.png` | `/admin/audit-logs` | Super Admin with audit viewing permission | Show filters and existing events only. The current seed may have no central audit rows; do not create business activity just to fill the screenshot. |

For dynamic routes such as period/order/receipt details, use the normal list link
to an existing synthetic record rather than assuming a numeric ID. Cross-check
the [route/permission inventory](ERP_V1_ROUTE_PERMISSION_INVENTORY.csv) and live
permissions before capture. The application enforces permissions on the server;
the role labels above are suggestions, not a substitute for permission checks.

## Suggested gallery order

The shot numbers are stable identifiers, not a ranking. Lead with Dashboard,
Human Resources, Inventory, Procurement and Finance. Follow
with Attendance/Leave and Payroll to demonstrate cross-module integrity. Add
Administration, IT, Help Desk and Audit views when their captured content is
useful. A short representative gallery is preferable to repetitive list images.
The complete plan still covers every major implemented module.

Optional follow-up images can show a mobile dashboard, an existing inventory
movement history, a budget detail, a ticket detail or a role-specific dashboard.
Keep desktop and mobile dimensions distinguishable in captions and filenames.

## Privacy and publication review

1. Verify the target and synthetic provenance before any browser interaction.
   Use approved demo sessions; never paste credentials into a browser URL.
2. Confirm every visible employee, organization, email address, reference number
   and financial amount is fictional. Use reserved example domains where email
   addresses are necessary. Exclude contact columns that add no portfolio value.
3. Keep passwords, tokens, signing keys, cookies, CSRF values, config contents,
   connection strings and local paths out of the frame. Do not capture HTML source,
   browser storage, network panels, reset-password dialogs or secret files.
4. Prefer framing/cropping or omitting sensitive columns. If redaction is needed,
   use opaque coverage and inspect the exported bitmap; do not modify source
   business records. Do not upload raw screenshots before this review.
5. Inspect every PNG for clipped navigation, horizontal overflow, missing CSS,
   unreadable tables, error flashes and unintended overlays. Check both the full
   image and its expected README display size.
6. Use concise, factual captions and alt text, for example: “Synthetic purchase
   order showing a partial receipt linked to inventory.” Avoid claims of commercial
   deployment, production certification or real-company outcomes.
7. Remove private metadata if any is present. Review the final asset and filename
   for secret values and local paths, then confirm the proposed Git diff contains
   only approved public documentation/assets. Never stage demo config files.
8. Validate image paths in the README and preview the Markdown before publication.

No database or application change is required to complete this plan. Any sample
data gaps and browser automation failures must be reported rather than hidden.
