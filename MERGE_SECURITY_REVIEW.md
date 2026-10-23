# Security and Procurement merge verification

Reviewed 2026-10-17 on feature/purchase-orders. Merge from main remains in progress; no merge commit created.

## Current mainline status (Assignment 2, 2026-10-23)

This document records the earlier merge checkpoint. Its IT write-permission and
Procurement navigation limitations were subsequently fixed by the merged
authorization/navigation work. They are not current unresolved vulnerabilities.
Best-effort audit durability and deployment HTTPS/proxy limitations still apply.
See [ERP_V1_CLEANUP_REPORT.md](ERP_V1_CLEANUP_REPORT.md) for the current audit and
the unresolved Payroll freshness release blocker.

## Resolution

- app.py retains Decimal validation plus centralized CSRF/session/fresh authorization imports.
- Receiving form retains both the CSRF partial and original submission_id field.
- All 137 feature route handlers and all 136 main handlers remain present. Compared with the feature parent, only index/login/logout handlers change; Procurement handlers retain their implementation.
- All changed existing feature templates are token-only additions except the expected base/login metadata and POST logout navigation changes. Horizontal navigation, print template, and PO controls remain intact.
- No business repository, permission policy, schema or migration was changed during resolution.

## Test integration fixes

Updated PO UI fixtures to use current request authorization and genuine CSRF tokens. Updated disposable Procurement/receiving runners to seed real role permissions, stamp secure sessions, submit genuine tokens, disable dotenv loading, and explicitly use testing configuration. No protection was disabled.

Extended the real receiving route/MySQL check: missing and invalid CSRF leave snapshots unchanged; explicit expired-token recovery preserves submission UUID; refreshed-token retry returns the existing receipt and leaves receipt count/stock unchanged. Permission revocation is exercised through the database.

## Results

- 160 Python tests passed, including session/CSRF, audit, validation and PO UI tests.
- 11 JavaScript tests passed.
- Disposable MySQL security, audit, Procurement, receiving, and cross-module security-review suites passed.
- Receiving suite verifies migration repeatability/historical compatibility, duplicate concurrency, independent deliveries, missing-stock-row races, rollback at six write stages, lost commit responses, over-receipts, and receiving/cancellation races.
- Actual Chrome local HTTP checks passed for login/logout, two tabs, expiry recovery, validation and cookie attributes. Initial sandbox browser attempt failed connecting to the debugging socket; elevated isolated retry passed.
- Python compilation, exact installed requirement pins, pip check and diff whitespace checks passed.
- No development/production database accessed or migrated. Migration executed only on disposable MySQL.

## Remaining checks and inherited limitations

Verify mobile/desktop visual layout, PO long descriptions and multipage printing manually. Production HTTPS, Secure cookies and proxy deployment remain unverified. Actual receiving expiry/retry is proven through Flask and real MySQL, not browser automation of receiving.

The existing Goods Receipt submission migration must be reviewed/applied explicitly by the operator before deploying to a database that lacks it; this review does not apply it there.

Previously documented permission-policy mismatches and best-effort audit behavior are unchanged: some IT/helpdesk writes use view permission, Procurement navigation also requires inventory.view, and audit storage failure can follow a committed business action. See SECURITY_REVIEW.md for session/deployment limitations.

Ready for approval to finalize this merge; this is not production deployment sign-off.
