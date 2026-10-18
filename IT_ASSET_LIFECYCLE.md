# IT Asset Lifecycle Step 1: state integrity and safe returns

Base: `1470da1` (Finance PR #6), branch `fix/it-asset-lifecycle`.
No new permission, role grant, financial policy or database migration is required.

## Existing states and transitions

Assets support AVAILABLE, ASSIGNED, MAINTENANCE, LOST and RETIRED. Conditions
(NEW/GOOD/FAIR/POOR/DAMAGED) are separate from lifecycle state.

| Action | Preconditions / transition |
| --- | --- |
| Create | UI creates AVAILABLE without an employee, ASSIGNED with an employee. Initial custody now writes one assignment-history row in the same transaction. |
| Edit | Metadata/condition/department changes; the edit repository does not change custody or lifecycle status. |
| Assign | AVAILABLE, no current employee and no open assignment history -> ASSIGNED; creates one custody record. |
| Return/unassign | Exactly one open history record matching the current employee and submitted assignment ID. ASSIGNED -> AVAILABLE. LOST rejects until recovery; MAINTENANCE rejects until completion, preserving custody/history. A valid legacy RETIRED return retains RETIRED. Department stays unchanged. |
| Start maintenance | AVAILABLE or ASSIGNED -> MAINTENANCE, retaining custody. Existing MAINTENANCE can only get a record if none is OPEN. LOST/RETIRED and duplicate OPEN maintenance reject. |
| Complete maintenance | MAINTENANCE with exactly one matching OPEN record -> ASSIGNED if still held, otherwise AVAILABLE. Closes maintenance atomically. |
| Mark lost | AVAILABLE or ASSIGNED -> LOST, retaining custody. Existing LOST, MAINTENANCE and RETIRED reject. |
| Retire | Normally AVAILABLE and unassigned -> RETIRED. Assigned, LOST, MAINTENANCE and already RETIRED assets reject. |
| Restore/recover | LOST/RETIRED -> ASSIGNED if custody remains, otherwise AVAILABLE. No invented historical records. |

The maintenance schema also defines CANCELLED, but no maintenance-cancellation
action currently exists. Completing COMPLETED/CANCELLED records rejects.

Approved return policy: LOST equipment must be recovered and MAINTENANCE equipment
must complete maintenance before returning custody. Both attempts fail inside the
locked transaction without closing assignment history or clearing the employee.
The Return control is hidden and managers see recovery/completion guidance.
After recovery/completion restores ASSIGNED, a normal return can proceed.
A RETIRED asset with custody is a legacy anomaly; its previously implemented
state-preserving return behavior is unchanged by this LOST/MAINTENANCE decision.

## Corrections and transactions

- Creation explicitly starts a transaction and saves the asset ID before inserting
  initial assignment history. Employee, selected asset department and acting creator
  become employee_id, department_id and assigned_by. assigned_at uses the same
  current-time default as normal assignment, not an invented backdated date.
  Either both rows commit or both roll back.
- Return locks the asset, then all open custody records, validates exactly one
  matching employee/expected assignment ID and checks open maintenance. It closes
  that exact history record (requiring one changed row) and clears current custody
  in the same transaction. ASSIGNED with OPEN maintenance is inconsistent and
  rejects rather than becoming AVAILABLE. LOST/MAINTENANCE returns reject before writes; legacy RETIRED state survives.
- The rendered return form now includes a required assignment ID. Duplicate returns
  and stale forms after return/reassignment, even to the same employee, cannot close
  a new assignment. Missing tokens require reload. This ID is concurrency context,
  not an authorization boundary or a replacement for CSRF.
- Assignment checks no orphan open history exists before adding another record.
- Maintenance completion previously locked maintenance then asset, opposite to
  creation. It now resolves the parent without a child lock, locks the asset first,
  locks/revalidates maintenance and checks the single OPEN record. It cannot revive
  a LOST/RETIRED asset from inconsistent old maintenance history.
- All affected writers roll back on validation/SQL/commit errors. Parent-first
  asset locking serializes cooperating operations per asset. Child locks follow
  the asset; return uses assignment history before maintenance. No automatic retry
  is performed after uncertain COMMIT responses.

Return GET rendering still uses separate read queries. In-flight changes may make
the displayed form stale, but transaction-time validation remains authoritative.

## Security and audit coverage

Existing `it_assets.view` and `it_assets.manage` requirements, independent Help Desk
permissions, per-request authorization and global CSRF remain unchanged. Viewers
cannot see management return controls or forge authorized returns. Missing or
inconsistent history hides the return form and displays a review warning to managers.
Rejected transitions cannot reach the success flash.

Current IT asset lifecycle routes do **not** emit central business-action audit
events. Assignment/maintenance history exists, but it is not a complete central
audit trail. This step preserves that behavior and does not invent success audits
or introduce unrelated audit integration. Central lifecycle auditing remains a
separate gap; user/login/security and other modules' audit behavior is unchanged.

## Database compatibility and legacy records

Existing IT asset, assignment and maintenance tables and their foreign keys are
required. Checked-in schemas leave storage engines to the server default. Tested
with disposable MySQL 8.0/InnoDB; actual deployments must verify InnoDB before rollout.
There is no database constraint guaranteeing one open assignment/maintenance record
or agreement between current asset state and history. Asset-first application locks
protect these workflows; direct SQL/imports can bypass them.

No company data was inspected, repaired or backfilled. Previously created assigned
assets may lack history. Missing/duplicate/mismatched open assignments now reject
return, and orphan open assignments reject assignment. Conflicting OPEN maintenance
requires review. Do not invent assigned_at, assigned_by, past custodians or closure
dates. Before rollout, an authorized read-only data review must identify affected
assets and obtain an approved repair process. A future uniqueness/consistency
migration requires separate review and legacy-data preparation.

Existing open browser tabs/scripts that omit assignment_id must reload/refetch.
Repository callers must supply the current assignment ID as the third argument;
omitting it fails safely. Unknown commit outcomes, possible deadlocks involving
other database writers and direct-SQL corruption remain operational risks.

## Tests and reproduction

- Full Python suite: 241 passed. JavaScript navigation suite: 11 passed.
- New `mysql_it_asset_lifecycle_smoke.py`: normal/exceptional-state returns,
  restoration/completion, initial history and saved asset ID, duplicate and stale
  same-employee returns, missing/duplicate/mismatched histories, SQL and pre-COMMIT
  rollback, real permissions/CSRF/revocation/disabled users and no false success/audits.
- Six real two-waiter races: return/return, maintenance/return, completion/return,
  assignment/return, assignment/maintenance and loss/return. Performance Schema
  verifies two distinct requesting InnoDB transactions are actually blocked before
  releasing the parent lock. INFORMATION_SCHEMA.INNODB_TRX did not reliably report
  their waits in this fixture, so it is not used as the success probe.
- Existing disposable IT Authorization/Help Desk, four Finance, central audit,
  security, Procurement, stock and receiving suites passed (11 suites including the
  new lifecycle suite). No company database was accessed.
- Chrome security/IT role checks passed with unchanged security flags, including
  manager/Super Admin assign/return using the rendered assignment ID, independent
  viewer controls, all 17 mutation routes, CSRF, revocation and disabled accounts.
  Added browser policy checks cover hidden LOST/MAINTENANCE return controls, stale
  POST rejection with unchanged history, then recovery/completion and successful return.
- Python/Jinja compilation, JavaScript syntax, dependencies and diff checks passed.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
.\.venv\Scripts\python.exe -B tests/mysql_it_asset_lifecycle_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_it_authorization_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_security_review.py
```

## Remaining policy decisions and manual checks

The LOST/MAINTENANCE return restriction is approved and implemented. Separate
approval is required for historical-data repair/backfill, department ownership rules versus
employee department, mandatory return condition/sign-off, central audit durability
or a database uniqueness migration. None is silently implemented here.

On a disposable synthetic instance:

1. Create assigned/unassigned equipment and inspect initial/current/history IDs,
   actors and timestamps. Edit metadata without rewriting historical custody.
2. Submit native Return, then repeat/reload. Use two tabs: return/reassign to the
   same employee, then submit the older form; verify rejection and intact new history.
3. Mark assigned equipment LOST and submit an old Return form: it must reject
   without changing custody/history. Recover, then return successfully. Start
   maintenance on assigned equipment: Return must reject until completion, then
   succeed once status is ASSIGNED. Both MySQL and Chrome automate these
   policy cases; native button interaction and fully styled layouts remain manual checks.
4. Inspect manager warning/absent Return for deliberately inconsistent synthetic
   history. Confirm viewer controls remain hidden and permission revocation works.
5. Check fully styled desktop/mobile forms and feedback. The Chrome runner blocks
   external HTTPS stylesheets; responsive visual acceptance and production HTTPS
   configuration remain unverified.

Await review before Step 2. No commit, push, merge or branch change performed.

## Additional Step 2 policy regressions

The approved LOST/MAINTENANCE return restriction remains mandatory. The additional
verification starts from `d425b10` and changes tests/documentation only, without
altering application state transitions, permissions or the existing legacy RETIRED
return behavior.

The disposable MySQL suite now explicitly proves:

- Recovery and maintenance completion work without any prior Return attempt, for
  both assigned and unassigned assets. Current custody/history is unchanged by
  recovery/completion, and a subsequent legitimate return succeeds when assigned.
- Retirement rejects assigned, LOST and MAINTENANCE assets. After recovery or
  completion, assigned custody must still be returned before retirement. Retired
  assets cannot be assigned, marked lost or sent into maintenance; restoration of
  a normally retired unassigned asset remains available.
- Six additional two-waiter InnoDB races cover recovery/return,
  recovery/maintenance, completion/retirement, duplicate completion, duplicate
  recovery and retirement/return. Together with the existing six, there are twelve
  observed-lock-wait concurrency scenarios. Expected results depend on lock order:
  blocked returns reject before recovery/completion, or succeed afterward; history
  remains open or closes exactly once accordingly. Duplicate recovery/completion
  commits once. Stale returns cannot close custody created after retirement/restore.

No lifecycle dead end was found in supported, consistent workflows. Contradictory
legacy data (for example, LOST with an OPEN maintenance record) still fails closed
and can require an approved data repair; this is not silently converted into a new
recovery or maintenance policy. No real data was inspected or repaired.

The full Python suite (241 tests), JavaScript suite (11 tests) and disposable
lifecycle suite passed. IT Authorization/Help Desk and session/security disposable
regressions, compilation and diff checks also passed.
No new browser behavior is introduced; the prior Chrome approved-policy coverage
remains, and the manual visual/native-interaction checklist above still applies.
