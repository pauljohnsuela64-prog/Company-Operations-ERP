# Inventory Step 1: manual stock transaction reliability

Started on feature/inventory-improvements with a clean tree at 898040c, identical to local main. No branch, commit, migration or company-record operations were performed.

Manual Stock In/Out use the existing Decimal validator for finite, positive quantities with at most two decimal places and a maximum of 9999999999.99. Repository validation also protects non-HTTP callers. Notes are limited to the existing 255-character column. Resulting balances are checked before the quantity update; arithmetic does not use floats. Exact withdrawal of 0.10 from 0.10 leaves zero.

Each transaction locks active item and warehouse records with FOR SHARE, then locks the warehouse/item balance. Stock In reserves a missing balance using the same atomic zero-row upsert as Goods Receiving. The reservation is rolled back on any later failure. Updated balance and the existing MANUAL_STOCK_IN/OUT movement (NULL reference ID) commit together. Master deactivation must wait until the stock transaction completes. Historical movements and Procurement code are unchanged.

Only pre-commit MySQL deadlocks/lock timeouts (1213/1205), followed by a confirmed rollback, retry up to three attempts. No automatic retry occurs after commit begins, after connection loss, or when rollback fails. Uncertain results tell the user to inspect movement history before resubmission. Retry tests cover this distinction, including a simulated lost commit response that persists exactly one movement.

## Verification

177 Python tests and 11 JavaScript tests pass. The new disposable MySQL stock suite covers exact quantities, insufficient/missing balance, invalid quantities and masters, aggregate overflow with strict mode disabled, concurrent missing/existing rows, competing withdrawals, manual IN/OUT, mixed Goods Receiving, ledger reconciliation, movement-insert rollback including a newly reserved row, master-deactivation locking, uncertain commit, actual forms, CSRF rejection and permission revocation. Existing disposable Procurement, receiving, security and audit suites also pass.

Run from the project root:

    .venv/Scripts/python.exe -m unittest discover -s tests -q
    .venv/Scripts/python.exe -u tests/mysql_stock_smoke.py
    node --test tests/horizontal_navigation.test.cjs

Each MySQL runner creates its own verified temporary datadir and synthetic database. Compatibility was checked on MySQL 8.0.46, InnoDB, existing DECIMAL(12,2) stock/movement columns. No application schema changes or new dependencies are required. Other database engines/versions and the actual company schema were not verified.

## Remaining limits

Manual submissions still have no persistent UUID: duplicate clicks, explicit expired-CSRF recovery, or uncertain-outcome resubmission can repeat a transaction. This is deliberately deferred to Inventory Step 2. Do not automatically replay an uncertain manual transaction. Goods Receipt UUID protection remains intact.

These are bounded concurrency checks, not load tests. Transactions can still exhaust their lock retries under contention. Stock Out on a genuinely absent row is rejected; a later independent Stock In does not imply that the earlier withdrawal should succeed.

No new Inventory business-action audit integration is introduced here. Existing audit/security regressions pass, and rejected test requests leave audit tables unchanged. Later approved work may add Inventory audit events, persistent manual submission tracking, and nonnegative database CHECK constraints after reviewing existing data. No such migration is required or applied in Step 1.

Manual browser verification remains: check Decimal validation messages and submitted values, stock-in/out permissions, an exact 0.10 withdrawal, and movement history on a synthetic test instance. No browser tests were run in this step.
