# Inventory Step 2 verification

Stock In/Out require a valid UUID, persisted on their single stock_movements row.
The nullable ASCII CHAR(36) column has a full unique index, preserving historical
and Goods Receipt movement compatibility through NULLs. No separate operation
table or coupling to the Goods Receipt repository is introduced.

Routes generate IDs on GET only. Every POST and validation redisplay retain the
submitted ID, and existing CSRF recovery preserves it as an opaque hidden field.
Missing/invalid IDs fail closed without opening a database connection. Fresh
session authorization and stock permissions remain required even for saved retries.

Results return the original movement ID with created=False for replay. New writes
return created=True for future audit integration. Equality checks include direction,
item, warehouse, quantity, notes and actor. Saved retries work even after stock is
fully withdrawn or a master record is subsequently deactivated; they do not write.
Existing Decimal validation, active-master shared locks, stock row locks, aggregate
limits and rollback protections remain intact for all new transactions.

Confirmed pre-commit lock failures retry at most three times after rollback, always
with the original UUID. Uncertain commits are not automatically replayed; users can
explicitly retry the original payload/key to retrieve the persisted result. The
unique constraint prevents two committing requests from claiming the same UUID.

Migration and backup/maintenance instructions are in database/migrations/README.md.
No company database was accessed or migrated. The change requires the migration
before deploying the new application; all workers must use matching code. Forms
opened before deployment without a submission ID are rejected rather than silently
assigned a new transaction key.

Verification covers 181 Python tests, 11 JavaScript tests, disposable MySQL Inventory,
Procurement, receiving, security and audit suites, compilation and diff checks.
Inventory checks include migration repeatability/interruption/incompatible schema,
historical data preservation, same/different UUID concurrency, changed details,
actor/direction conflicts, cross-item collisions, lost-response recovery, rollback
and key reuse, exact quantities, depleted-balance retries, separate legitimate
operations, master locking, CSRF expiry/renewal, authorization and Goods Receiving.
Compatibility is checked on MySQL 8.0.46 with InnoDB and DECIMAL(12,2).

Remaining limits: a new form/new UUID represents a new transaction; it cannot detect
manual re-entry of an already saved operation. Historical NULL-key operations cannot
be deduplicated retroactively. Persistent keys must not be removed or changed while
retries are possible. Future audit integration must check created, and durable audit
delivery remains a separate design. No Inventory audit feature is added here.

Manual browser checklist (not run this step): double-click and repost each form;
retry an expired-CSRF form with its original UUID; renew CSRF without reopening the
stock form; verify one movement/balance update; change a payload under the same UUID
and confirm rejection; open a fresh form for an independent operation; check missing
UUID rejection, permission revocation, validation redisplay and receipt integration
using synthetic records only.
