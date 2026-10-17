# Procurement validation and display policy

Supplier fields follow the existing MySQL schema: code 30, name 150, contact person 100, email 150, phone 30 and address 255 characters. Purchase Request purposes are limited to 255 characters. Validation errors return to the existing form without a write or success message.

Adding or replacing a PR item requires an existing active inventory item. The repository locks the DRAFT parent first and checks the item with a shared row lock inside the same transaction, preventing concurrent deactivation before commit. Existing historical items are not rewritten.

Procurement navigation requires procurement.view, matching its list routes; inventory.view is not required. Backend action permissions and approval ownership rules are unchanged.

Currency display uses Decimal ROUND_HALF_UP to cents: 10.25 ? 2.50 = 25.625 displays as PHP 25.63. Each PO line is rounded separately, then displayed lines are summed for the order total. PO detail, PO print and receipt line displays use the shared currency formatter with grouping and two decimal places. Quantities retain their existing display. No stored costs, receipts, stock or historical financial data are changed. Separate receipt lines round independently and may therefore differ by a cent from rounding an aggregate delivery value.

No schema migration is required. Schema checks run only on disposable MySQL. Local schemas that differ from the versioned SQL still need operator review; this work does not inspect company databases.

Manual verification: add/edit supplier with an overlong field; create an overlong PR; forge inactive/missing item IDs; confirm procurement-only user navigation and denied backend actions; compare PO/printed PO and full-receipt half-cent displays; confirm existing CSRF expiry recovery retains the delivery UUID.
