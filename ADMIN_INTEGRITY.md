# Administration access integrity

`update_user_role` and `set_user_active_status` share `_write_user_access`.
Both require keyword-only `actor_user_id`; self role/status changes reject at
the repository boundary as well as in the HTTP routes. Actor authorization still
uses the existing request-start refresh; this is not transaction-time revocation.

## Transaction and lock order

1. Validate positive signed-INT user/actor/role identities and exact Boolean status.
2. Start READ COMMITTED and lock the existing `users.manage` permission row
   `FOR UPDATE`. This is an InnoDB serialization guard, not a permission/grant
   change. Missing guard fails closed (503); no row is provisioned automatically.
3. Read/hold the canonical Super Admin role `FOR SHARE`, then lock the target user
   `FOR UPDATE`. Missing canonical role fails closed (503); missing target is 404.
4. Validate a requested role under `FOR SHARE`. Missing role is 400. Compare
   persisted values; an unchanged request returns `changed=False` after rollback.
5. Before removing an active member of the Super Admin role, count current active
   members using a nonlocking READ COMMITTED read after the guard. Reject the last
   member's removal/deactivation with 409. Both writers retain the guard to commit.
6. Update the locked user and return its username/changed result only after commit
   and successful cleanup. Rejected writes roll back; no success audit is attempted.

The shared guard makes cooperating access writers serial. The count sees a prior
writer's commit even after waiting, without locking other users out of order.
Ordinary role reads remain shared: an exclusive Super Admin role guard would
conflict with Help Desk's user-then-role assignment reads. The permission guard
avoids that role/user inversion. Role-permission editing can contend via its
permission foreign keys but does not acquire user locks in that transaction.
Other writers can still cause deadlocks/timeouts; 1205/1213 return 409 after rollback,
with reload/review guidance and no automatic retry. No global MySQL setting changes.

The guarantee preserves at least one active canonical Super Admin when starting
from valid state. Existing zero-admin data is not repaired or fabricated. Valid
promotion/reactivation can restore membership through an already-authorized actor;
external recovery still needs its own explicit authorization.

## Forms, results and auditing

Status forms send `is_active=0` or `1`; there is no legacy toggle fallback. Missing,
invalid or duplicate targets return 400 and require reloading old tabs/scripts.
Repeated or stale same-target status submissions cannot reverse account status.
An explicit opposing target can still supersede an earlier change; no optimistic
revision token is introduced. Role changes remain explicit role assignments.

Changed commits attempt ADMINISTRATION / UPDATE (role), ACTIVATE or DEACTIVATE
with the locked username identity and a fixed bounded description. Passwords,
hashes, grants, tokens and session metadata are excluded. Unchanged requests show
information and emit no success audit. The audit transaction remains best effort;
an audit outage cannot undo a confirmed account update.

A lost COMMIT acknowledgment or cleanup failure returns 503 without success audit;
rollback attempts do not establish noncommit. Reload/reconcile persisted role/status
before retrying. Missing audits do not prove rollback, and no audit is reconstructed
by a later no-op retry. Password-change session invalidation and authorization/CSRF
refresh are unchanged. No schema migration or grant is required by this change.

## Other writers and boundaries

All HTTP role/status writes use the shared helper. The obsolete unreachable copy
of the old toggle after the Role Permissions view was removed. The count reader
remains an advisory API, never an authority for access writes.

User creation and `create_super_admin.py` add accounts and cannot remove an active
admin; password reset/login timestamps do not alter role/status. Existing
`update_role_permissions` semantics and Super Admin permission-edit protection in
the HTTP view are unchanged. This invariant concerns canonical role membership,
not whether every role retains specific grants. Direct repository role-permission
calls, role/permission renames/deletions, direct SQL, external imports, old workers
and restored data can bypass these conventions. Coordinate compatible writers;
the schema gate is not an external-writer fence. No permission policy is invented.

## Verification

- `tests/test_admin_integrity.py`: input/self protection, explicit targets,
  postcommit changed/no-op/error audit boundaries, permissions and real CSRF.
- `tests/mysql_admin_integrity_smoke.py`: actual routes/repositories and observed
  InnoDB waits for cross-deactivation, cross-demotion and both mixed orderings;
  last-admin protection, valid recovery, no-ops, missing references, SQL/precommit
  rollback, real lock timeout, uncertain commit, audit SQL outage and security.
- `tests/mysql_admin_integrity_browser.py` / `browser_admin_integrity.cjs`: the
  existing isolated security/IT Chrome review plus native status/role controls,
  replays, self controls, last-admin rejection, CSRF/permission denial and exact
  persisted account/audit checks. Native Chrome is separate from hosted CI.
- Existing business-audit fixtures now supply explicit status intent and the
  repository result/guard contract while retaining commit/audit assertions.

Smoke discovery automatically includes the new MySQL suite. Tests create verified
fresh loopback servers and synthetic authorization fixtures only; they never change
company databases or production permissions. Actual deployment, TLS and scale need
separate qualification. No Payroll/HR Lifecycle functionality is changed.
