# Procurement business-action audits

All new events use record_audit_event(), module PROCUREMENT, the freshly authorized session actor, and the numeric supplier/PO/receipt ID in entity_id. Descriptions include the supplier code or PO/receipt number and numeric ID. RECEIVE also includes the related PO number and ID. No supplier contact/name/address, notes, passwords, CSRF tokens or submission UUIDs are logged.

| Entity | Actions |
| --- | --- |
| SUPPLIER | CREATE, UPDATE, ACTIVATE, DEACTIVATE |
| PURCHASE_ORDER | CREATE, UPDATE_COST, MARK_SENT, CANCEL |
| GOODS_RECEIPT | RECEIVE |

Events are called only after repository success/commit. Existing Purchase Request SUBMIT, APPROVE and REJECT integration is unchanged. The best-effort audit helper catches write/lookup failures; business transactions are not undone by audit failures. Cancellation retains its numeric identifier if the optional PO-number lookup fails.

The receipt repository still returns a three-element tuple-compatible result (receipt ID, number, status). Its internal created flag is true only after a new receipt commits and false for existing-UUID results, including concurrent retries and duplicate-key recovery. Only the creating HTTP request emits RECEIVE. Separate legitimate deliveries have separate receipt IDs and events. Direct repository calls, like other business repository calls, do not independently create HTTP action audits.

## Durability limitation

This follows existing ERP best-effort auditing, not transactional outbox delivery. An audit outage, process crash after business commit, or lost commit acknowledgment can leave an action without an audit row. UUID replays do not backfill a missing event; this prevents retry-generated duplicates. After an audit write failure, the committed receipt and stock remain intact. Durable eventual auditing would need a separate approved design. Historical receipts are not backfilled.

## Verification

170 Python tests and 11 JavaScript tests pass. Disposable MySQL Procurement, receiving, security and audit suites verify persisted identities/actions, unchanged PR auditing, concurrent UUID replay, separate deliveries, rollback and trigger-induced audit insert failure isolation. No company database is read or migrated. No schema or dependency changes are required.

Manual checks on a test instance: perform each new action, search/filter Audit Logs by PROCUREMENT/action and readable identifier, inspect actor/entity/description, retry a receipt with its original UUID and confirm one RECEIVE row, and confirm two independent deliveries have two rows. Browser checks were not run for this change.
