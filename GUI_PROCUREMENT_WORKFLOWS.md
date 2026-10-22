# GUI Phase 3A: Procurement workflows

Fourteen Procurement screen templates adopt the Phase 1/2 navy/slate foundation:
six Purchase Request, four Purchase Order and four Goods Receipt screens. The
standalone `orders/print.html` document is unchanged and does not inherit screen
CSS. No application Python/JavaScript, route, repository, schema, transaction,
calculation, permission or approval-separation policy is changed.

## Presentation and reusable components

Screen wrappers opt in through `workflow-page workspace-page`. They reuse Phase 2
color/spacing/radius/elevation tokens, controls, table regions, table typography
and status surfaces. Workflow-specific panels and wrapping action groups retain
complex status/permission conditions rather than moving decisions into a generic
component. Form pages have consistent headings, required indicators, spacing and
full-width mobile actions. Disabled contextual fields remain visibly read-only.

`workspace_components.workflow_status` is a presentation-only macro for Draft,
Submitted, Approved, Rejected, Completed, Cancelled, Sent, Partially Received and
Received labels. It retains the manually-issued Sent wording on PO detail pages.
Unknown labels remain escaped. Distinct text/color states do not enable actions.
All original action checks, POST methods/actions, CSRF fields, confirmation text,
field names/constraints, hidden values and URL generation are preserved.

Tables have captions, scoped column headings and named, focusable horizontal
scroll regions. Long identifiers/notes wrap; price cells retain their original
formatters and expressions and avoid broken currency strings. Metadata and action
areas wrap on narrow screens. Positioned table regions contain absolutely
positioned accessible labels as well as wide tables, preventing receiving-label
overflow outside the scroll container.

Receiving retains submission_id and every quantity_received_<item_id> field,
including existing min/max/step/value semantics. Labels identify each item's
quantity control. Explanatory text emphasizes quantities delivered now and the
remaining balance. Already received amounts are not represented as receivable.
The pre-existing form/div nesting is corrected without changing field ownership.
No client-side search, sorting, pagination, business calculation or script is added.
Existing backend failures retain their existing handling; no new fallback masks them.

## Verification

The full Python suite includes action visibility, linked PO eligibility, quantities,
Decimal totals, print escaping/A4 rules, authentication, permission and CSRF checks.
Procurement, Receiving and atomic PO Supplier eligibility disposable MySQL suites
cover concurrency, rollback, duplicate protection, idempotency and historical
receiving after supplier deactivation. A separate isolated render comparison
against main verifies methods/actions, controls and links across 14 templates,
nine statuses and authorized/read-only contexts (252 comparisons).

Run `tests/mysql_gui_procurement_browser.py` with the existing installed MySQL and
Chrome. Set ERP_GUI_BOOTSTRAP_CSS to a temporary copy of the existing Bootstrap
5.3.8 stylesheet and ERP_GUI_SCREENSHOTS to a temporary artifact directory. The
runner uses the unchanged disposable server identity/cleanup guards. It composes
base browser login/session/CSRF checks with the Procurement review; unrelated IT
browser checks remain in their existing suite. CDN CSS is fulfilled locally via
CDP, other external browser requests are blocked, and Chrome security flags are
unchanged. Only synthetic fixture roles receive existing permission codes; no
production grants or policies are changed.

The manager/requester lacks approval permission, the separate approver lacks
creation/order/receiving management, and the reader has only Procurement view.
Chrome reviews all five widths (1440/1024/768/390/320, 1000px viewport height),
empty/populated lists, long/escaped notes, forms and validation, request status
transitions, inactive Supplier rejection, duplicate PO redirection, item-cost
editing, precise 25.63 totals, send/cancel and partial/final receiving. Receipt
validation must retain submission_id; identical replay must return the existing
receipt. A new delivery uses a new UUID and remaining quantity. The fixture's
final DB proof requires exactly two receipts, two stock movements and two RECEIVE
audits totaling 10.25, with Finance history and role grants unchanged. It also
checks historical receiving after Supplier deactivation, read-only denials and
invalid CSRF. Chrome emits screenshots and an A4 PO PDF to temporary storage.

## Limits and operational safeguards

Physical-device, screen-reader, translated-text and production-capacity validation
remain outstanding. Wide tables intentionally scroll within their own regions.
Existing list-reader performance and snapshot behavior are unchanged. PR status
labels do not invent unavailable lifecycle actions. The browser's synthetic
Procurement fixtures do not activate Payroll or HR Lifecycle work. No migrations,
company DB operations, production grants, deployment, push or merge are performed.
Recurring hosted disposable MySQL startup failures, if present in the latest CI
run, remain separate from this presentation change; no timeout, identity or
cleanup safeguard is weakened.

## Recorded verification (2026-10-22)

- 516 Python tests and 11 JavaScript navigation tests passed.
- Disposable Procurement, Receiving and PO Supplier Eligibility suites passed.
- All 110 Jinja templates parsed; 163 Python and 24 JavaScript syntax checks,
  dependencies and whitespace checks passed. The rendered main-versus-GUI contract comparison
  passed all 252 cases.
- The final Chrome run passed with manager, approver and read-only accounts at
  1440, 1024, 768, 390 and 320px. Representative screenshots were visually reviewed
  across those widths. Native button clicks exercise existing confirmations;
  the initial test helper's requestSubmit bypass was corrected in the test only.
  There were no captured JavaScript exceptions/console errors or page-wide
  overflow. The generated PDF has an A4 page box; the print template is unchanged.
- Final database assertions confirmed exactly two receipts, stock movements and
  RECEIVE audits totaling 10.25, no replay duplicates and unchanged Finance history
  and fixture grants. The disposable server shut down and its directory was removed.
- Main CI run 39746807026, head d297f3858da25dfd23e6fd216d1bef763b7d8bd7,
  completed successfully, including its disposable MySQL job.
