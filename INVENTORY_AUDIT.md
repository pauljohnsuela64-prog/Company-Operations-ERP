# Inventory Step 4: business-action audit integration

## Events and payload

All events reuse record_audit_event(), module INVENTORY, the existing freshly
authorized session actor, and numeric entity_id. Descriptions include stable
numeric IDs and readable master codes, not names, locations, notes, descriptions,
passwords, CSRF tokens or submission UUIDs.

| Entity type | Actions |
| --- | --- |
| INVENTORY_CATEGORY | CREATE, UPDATE, ACTIVATE, DEACTIVATE |
| WAREHOUSE | CREATE, UPDATE, ACTIVATE, DEACTIVATE |
| INVENTORY_ITEM | CREATE, UPDATE, ACTIVATE, DEACTIVATE |
| STOCK_MOVEMENT | STOCK_IN, STOCK_OUT |

Creation repositories return their committed numeric IDs without extra lookup
queries. Updates use existing request IDs/codes. Activation/deactivation returns
whether a row actually changed; stale/no-op or missing-row transitions do not
produce success events or success messages. Existing activation policy is unchanged.

Stock routes use the existing StockResult.created flag: only a newly committed
movement emits an event. An existing UUID result does not log again, including
concurrent retries, depleted-balance retries, or explicit renewed-CSRF retries.
New UUIDs produce distinct movements and events. Stock descriptions include the
movement ID, item code/ID and warehouse code/ID, using lists already fetched by the
route; there are no extra post-commit identifier queries. Labels reflect that
request's loaded master data; numeric references remain authoritative.

## Transaction and security behavior

Events execute after successful repository commits, using the existing separate,
best-effort audit transaction. Validation failures, business/commit exceptions,
CSRF rejections and permission denial never reach the success event calls.
Stock balance/movement/UUID atomicity and Procurement audit integration are
unchanged. No schemas, migrations, business-policy restrictions, permissions or
GUI changes are introduced. Company records are not accessed or modified.

Best-effort is not durable delivery: audit outages, crashes after business commit,
lost commit acknowledgments or other post-commit failures can leave an action
without an event. A saved UUID retry does not backfill that missing event. Audit
insert failures do not roll back committed business data. Guaranteeing durable
eventual audit delivery would require a separately approved outbox/recovery design.
Master-data edits are not submission-idempotent: independent successful edit
requests each generate an event, even when values are unchanged.

## Automated verification

194 Python tests and 11 JavaScript tests pass. Disposable MySQL master-data,
Inventory stock, Procurement, receiving, security and audit suites pass. The new
checks verify all 14 event types, actors, numeric IDs/readable labels, unchanged
history/balances for master edits, sensitive-value exclusion, no-op status handling,
rejected requests, concurrent stock UUID deduplication, distinct transactions,
trigger-induced business rollback, lost acknowledgment and audit SQL failure
isolation for master creation/update/status and manual stock operations.
Compilation, dependency and diff checks pass. No development/production migration
is applied; existing migration regression checks run on disposable servers only.

The two pre-existing untracked Step 3 test files were preserved. The master-data
MySQL suite was extended for audit expectations; the validation unit file was
not changed.

## Manual browser checklist

On an isolated instance with synthetic records and an authorized Audit Logs user:

1. Perform create/edit/deactivate/activate on each master type. Filter Audit Logs
   by INVENTORY/action and inspect actor, entity type, numeric ID and readable code.
2. Perform Stock In/Out and inspect movement/item/warehouse references. Replay the
   original UUID after success and after expired-CSRF recovery; confirm one event.
3. Use a new form/UUID for a legitimate separate transaction and confirm a new event.
4. Verify invalid forms and users without management permission cannot produce events.
5. Confirm sensitive notes/locations/names do not appear in audit descriptions.

Browser automation was not run for this step. Inventory Manager does not gain
Audit Logs permission automatically; use an existing authorized audit role. The
pending unit-change, inactive-category and deactivation-with-stock policies remain
as documented in INVENTORY_MASTER_DATA.md; no new restrictions are imposed here.
