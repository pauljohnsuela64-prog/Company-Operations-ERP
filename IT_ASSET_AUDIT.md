# IT Asset Step 3: business-action auditing

Baseline: `fix/it-asset-lifecycle`, checkpoint `afe3eef`. No schema, migration,
permission, role-grant or lifecycle policy changes are required.

## Events and identity

All events use the central `record_audit_event()` helper, module `IT_ASSETS`,
and its authenticated session actor. Numeric IDs remain the canonical targets;
readable identifiers appear in concise descriptions.

| Entity type | Actions | Numeric target | Readable identifier |
| --- | --- | --- | --- |
| IT_ASSET | CREATE, UPDATE, ASSIGN, RETURN, MARK_LOST, RECOVER, RETIRE, RESTORE | Asset ID | Asset tag |
| IT_ASSET_CATEGORY | CREATE, UPDATE, ACTIVATE, DEACTIVATE | Category ID | Category code |
| IT_ASSET_MAINTENANCE | CREATE, COMPLETE | Maintenance ID | Asset tag; description also includes asset ID |

The existing restore endpoint emits RECOVER for a committed transition from LOST
and RESTORE for a committed transition from RETIRED. Its repository returns the
previous state captured under the existing asset lock, avoiding classification
from a stale page or a later lookup. No new lifecycle action exists.

Creation with initial custody emits one CREATE event and retains the existing
atomic assignment-history insert. It does not invent a separate assignment request.
Maintenance events identify their history record rather than replacing its ID
with an asset tag. No employee names, costs, maintenance descriptions, notes,
vendor details, authentication secrets or entire form payloads are copied.

## Commit boundary and duplicates

Routes audit only after repositories return from successful business commits.
Existing transaction SQL, locking order and rollback boundaries are unchanged.
Repositories now return success/change information; metadata/category updates
report MySQL affected rows, and restore returns its locked previous state.
Unchanged updates do not show a success flash or emit an UPDATE event.
Existing exceptions and false results produce no success event.

Lost/maintenance return blocks, retirement safeguards, stale assignment tokens,
duplicate transitions and asset-first locking remain in force. Concurrent
same-intent category status writes audit only the actual changed row. A later
sequential toggle remains a legitimate opposite action under existing semantics.
Read requests, permission denials and CSRF failures never reach business auditing.

The central helper isolates both identifier lookup failures and audit storage
failures. Business success remains committed; failed lookup may leave only the
numeric identity. Postcommit tag/code lookups can reflect a subsequent rename.
This is the established best-effort model, not durable exactly-once delivery:
a crash between business commit and audit insert or an audit outage can leave
an operation unlogged. There is no outbox, UUID, retry or historical backfill.
Direct repository/SQL writers remain outside route-level auditing.

## Verification

`tests/test_it_asset_audit.py` covers fourteen action variants, actors and identity,
minimal payloads, rejected/no-op writes, lookup/storage failure isolation,
locked-state recovery classification, GET requests, fresh authorization and CSRF.

`tests/mysql_it_asset_audit_smoke.py` uses fresh disposable MySQL and synthetic
records. It checks every event, repeated/stale/blocked transitions, real trigger-
induced rollback and audit INSERT failures, nine actual concurrent asset write
races, a concurrent category status race, denied requests, revocation and disabled
accounts. Existing lifecycle and validation suites retain their transaction,
Decimal and return-policy checks; successful web validation now expects audits.

Verification completed: 256 Python tests, 11 JavaScript tests, thirteen disposable
MySQL integration suites, and the separate Chrome/disposable-MySQL security review
passed. The MySQL suites covered IT auditing/lifecycle/validation/authorization,
Finance payment/validation/reporting/audit, Inventory stock, Procurement,
receiving, security and central Audit Logs. Python/Jinja compilation, JavaScript
syntax, dependency consistency and diff checks passed.

Real Chrome passed native forms, both viewer roles, IT Manager and Super Admin,
forged POST/CSRF denial, revocation/disabled accounts, blocked returns followed
by recovery/completion and normal return, and central IT audit display/filtering.
Chrome checks DOM/native workflows; external styles are blocked by the existing
harness, so fully styled desktop/mobile acceptance remains manual. Production
TLS/Secure-cookie behavior is not certified by the HTTP test environment.

## Manual acceptance and operational limits

In an approved synthetic environment, use an IT manager and an audit viewer:

1. Create and edit an asset, assign/return it, mark lost/recover it, retire/restore
   it, and confirm one correctly attributed event per committed operation.
2. Create/edit/toggle a category and create/complete maintenance. Check module
   filtering, numeric targets and readable tags/codes in central Audit Logs.
3. Repeat completion/return, submit a stale assignment token, and try returning
   LOST/MAINTENANCE assets. Confirm validation and unchanged audit counts; recover
   or complete maintenance, then confirm a normal return succeeds.
4. Verify view-only users have no mutation controls; revoked/disabled users and
   missing CSRF requests cannot mutate or add success events.
5. Review styled desktop/mobile layout and long identifiers, plus production HTTPS
   and Secure-cookie configuration through the normal deployment process.

No existing company records are backfilled or repaired. Employee eligibility,
department ownership and stronger audit durability remain separate policy work.
Await review before Step 4; no commit, push, merge or branch change is authorized.
