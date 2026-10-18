# IT Asset and Help Desk authorization ? Step 1

## Scope and original defect

At base commit 8a38f60, all 26 Asset/Help Desk route functions used
`it_assets.view`, including 17 POST-capable functions. A valid CSRF token plus
asset-view permission therefore authorized asset and ticket changes. Hiding links
could not prevent forged requests. Help Desk navigation already used
`helpdesk.view`, while its backend incorrectly required asset view.

The existing seed defines all four permissions below and assigns them to both
Super Admin and IT Manager. Reuse `helpdesk.*`; do not create `help_desk.*` aliases.
No new permission names or schema columns are needed.

| Permission | Access |
| --- | --- |
| it_assets.view | Asset list/detail, categories, reports and export |
| it_assets.manage | Asset/category creation/editing, assignment/return, maintenance, loss/recovery/retirement |
| helpdesk.view | Ticket list/detail, reports and export |
| helpdesk.manage | Ticket creation, assignment, start, resolution and closure |

Management forms require manage permission on GET as well as POST. Ordinary
read-only GET pages remain available to their module's viewers. Permissions are
independent: manage does not implicitly grant view. Operational managers should
receive both permissions for the module. No role-name bypass is added.

## Backend and UI

The existing `permission_required` decorator checks fresh request-local
permissions loaded by `security.init_security` from the database. Neither that
loader nor CSRF configuration/exemptions changes. The existing unauthorized
redirect to `/dashboard` (or `/login` for unauthenticated users) is preserved.
All mutation controls use matching manage checks, with existing status checks
retained. The dashboard gates the two cards independently; horizontal navigation
already has the correct separate view checks and its structure/JavaScript remains
unchanged. Repositories remain internal business operations called after route
authorization; no transaction, lifecycle, calculation or audit behavior changes.

## Complete route inventory

HEAD/OPTIONS retain Flask's normal behavior; these are the explicit route methods.

| Route | Methods | Required permission |
| --- | --- | --- |
| `/it/assets` | GET | `it_assets.view` |
| `/it/assets/add` | GET, POST | `it_assets.manage` |
| `/it/assets/<int:asset_id>` | GET | `it_assets.view` |
| `/it/assets/<int:asset_id>/edit` | GET, POST | `it_assets.manage` |
| `/it/assets/<int:asset_id>/assign` | POST | `it_assets.manage` |
| `/it/assets/<int:asset_id>/unassign` | POST | `it_assets.manage` |
| `/it/assets/<int:asset_id>/maintenance/add` | GET, POST | `it_assets.manage` |
| `/it/assets/maintenance/<int:maintenance_id>/complete` | POST | `it_assets.manage` |
| `/it/assets/<int:asset_id>/retire` | POST | `it_assets.manage` |
| `/it/assets/<int:asset_id>/lost` | POST | `it_assets.manage` |
| `/it/assets/<int:asset_id>/restore` | POST | `it_assets.manage` |
| `/it/assets/categories` | GET | `it_assets.view` |
| `/it/assets/categories/add` | GET, POST | `it_assets.manage` |
| `/it/assets/categories/<int:category_id>/edit` | GET, POST | `it_assets.manage` |
| `/it/assets/categories/<int:category_id>/status` | POST | `it_assets.manage` |
| `/it/assets/reports` | GET | `it_assets.view` |
| `/it/assets/reports/export` | GET | `it_assets.view` |
| `/it/help-desk` | GET | `helpdesk.view` |
| `/it/help-desk/reports` | GET | `helpdesk.view` |
| `/it/help-desk/reports/export` | GET | `helpdesk.view` |
| `/it/help-desk/add` | GET, POST | `helpdesk.manage` |
| `/it/help-desk/<int:ticket_id>` | GET | `helpdesk.view` |
| `/it/help-desk/<int:ticket_id>/assign` | POST | `helpdesk.manage` |
| `/it/help-desk/<int:ticket_id>/start` | POST | `helpdesk.manage` |
| `/it/help-desk/<int:ticket_id>/resolve` | POST | `helpdesk.manage` |
| `/it/help-desk/<int:ticket_id>/close` | POST | `helpdesk.manage` |

## Role mapping and repeatable upgrade

| Existing role | Intended permissions |
| --- | --- |
| Super Admin | All four, preserving the existing administration path |
| IT Manager | All four, matching the existing seed's explicit remit |
| Other standard roles | No added grants |
| Custom roles | Preserve current grants; review missing grants individually |

`seed_roles_permissions.py` already contains this mapping and needs no change.
Do not rerun its broad seeding process just for this fix: it also touches unrelated
permissions. `database/migrations/003_it_helpdesk_permissions.sql` is a narrow,
transactional, repeatable alternative. It inserts missing permission definitions
and missing grants only for existing Super Admin/IT Manager roles. It creates no
roles, changes no users, copies no grants from asset viewers, and removes nothing.
Repeated execution produces the same four definitions/eight canonical grants
when those two roles exist. It does not reinterpret custom role names.

Review/deployment procedure (not executed against company databases):

1. A database administrator explicitly selects and verifies the target database
   and takes a backup/export of permissions, role_permissions, roles and users.
2. Review current grants and confirm that canonical role names still match the
   organization's policy. Identify custom administrators and support roles that
   currently depend on `it_assets.view`; get explicit approval for any additional
   view/manage grants. Do not mechanically promote every viewer to manager.
3. Verify an active administrator has `users.manage` and `roles.manage`, and that
   Super Admin and IT Manager roles exist when those paths are expected. If names
   or custom mappings are ambiguous, stop that mapping change for policy approval.
4. Review and apply only 003 to the explicitly selected database. Verify its grants
   before deploying the route change in a coordinated release. If all four grants
   already exist for the intended operators, no data migration is necessary.
5. Confirm viewer/manager behavior using synthetic acceptance accounts. Existing
   sessions receive committed grant changes on their next request.

Only disposable MySQL was used during implementation. The SQL has no automatic
application startup hook and no connection configuration. Reverting application
code reintroduces the original vulnerability; prefer correcting grants rather
than rolling back the authorization boundary. Use the pre-upgrade grant snapshot
for any approved data rollback; do not delete shared existing permissions.

Read-only preflight query for the administrator's review:

```sql
SELECT r.role_name, p.permission_code
FROM roles r
LEFT JOIN role_permissions rp ON rp.role_id = r.role_id
LEFT JOIN permissions p ON p.permission_id = rp.permission_id
WHERE r.role_name IN ('Super Admin', 'IT Manager')
   OR p.permission_code IN ('it_assets.view', 'it_assets.manage', 'helpdesk.view', 'helpdesk.manage')
ORDER BY r.role_name, p.permission_code;
```

## Policy decisions deliberately left open

The existing seeds clearly establish the canonical role mapping. They do not
establish ticket-owner or assignee-only authority. This step retains existing
workflows within `helpdesk.manage`:

- Whether employees can create/view only their own tickets needs an explicit
  self-service permission and row-level policy; current view grants module-wide access.
- Whether only the assigned technician may start/resolve a ticket, whether the
  requester must confirm closure, and whether dispatch requires a separate grant
  need business approval. Managers may currently operate any ticket.
- Technician choices remain active Super Admin/IT Manager accounts. Replacing the
  existing hardcoded eligibility with permissions, or allowing additional roles,
  requires an approved assignment policy.
- Custom-role grants and stronger separation among asset lifecycle actions require
  review; no such grants or restrictions are inferred here.

## Verification

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
.\.venv\Scripts\python.exe -B tests/mysql_it_authorization_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_security_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_audit_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_security_review.py
git diff --check
```

The new unit contract checks all 26 routes, all mutation/form denials, module
isolation, live permission revocation, disabled accounts, anonymous access,
CSRF and independent dashboard visibility without company database access.
The new MySQL runner reuses the existing temporary-server harness (`--no-defaults`,
fresh temporary datadir, loopback port, verified `@@datadir`, graceful shutdown).
It tests the upgrade twice, no unrelated grants, all 17 authorized writes, all
17 viewer/unauthorized/CSRF denials with unchanged business/history/audit snapshots,
real templates and exports, action controls across lifecycle states, navigation,
database-backed revocation and disabled accounts. It never loads ERP dotenv settings.
Existing security/audit suites check compatibility; no new audit events are added.

Browser acceptance checklist using synthetic accounts/data:

- Asset-only viewer: Assets navigation/card, list/detail/categories/reports/export
  work; Help Desk navigation/card absent; no asset mutation controls.
- Help Desk-only viewer: Help Desk navigation/card and read/report/export work;
  Assets navigation/card absent; no ticket mutation controls.
- IT Manager: both modules, all forms and appropriate status actions work; verify
  assignment/return/maintenance/lost/restore/retire and ticket assign/start/resolve/close.
- Repeat at desktop/mobile widths; horizontal menus, focus and Escape behavior
  stay intact. Check pages for console errors and layout regressions.
- Forge a POST with a valid token as a viewer: redirect, no persisted changes.
  Remove a manager grant in the disposable DB: next request denies. Disable the
  synthetic account: next request requires login. Missing/invalid token: HTTP 400.

Deployment risks: users/custom roles that previously relied solely on asset view
will intentionally lose write access and incidental Help Desk access. Review
these mappings before rollout. Fresh authorization is per request, so a request
already authorized before a concurrent revocation can still complete. Other
previously assessed lifecycle/validation/audit gaps remain separate work.


## Final authorization verification

Ready for a Git checkpoint and a pull request for Step 1. No application security
or migration SQL changes were needed during final verification. This verdict is
for review of the authorization change, not production deployment approval.

- Branch verified: `fix/it-helpdesk-authorization`; uncommitted changes inspected.
- All 26 route functions rechecked: 12 Asset mutations require `it_assets.manage`,
  five ticket mutations require `helpdesk.manage`, five Asset read routes require
  `it_assets.view`, and four ticket read routes require `helpdesk.view`.
- Migration 003 applied twice on disposable MySQL. Existing custom viewer grants
  remained unchanged; Super Admin and IT Manager each received exactly four IT
  permissions; unrelated roles received none. The existing seed already defines
  these names/mappings. No company database upgrades were performed.
- Complete Python suite: 207 tests passed; complete JavaScript unit suite: 11 passed.
- Disposable IT authorization, session/CSRF and business audit MySQL suites: passed.
- Cross-module review: all nine module database checks passed.
- Real Chrome 155 browser checks: passed against loopback HTTP and disposable MySQL.
- Python/Jinja compilation, JavaScript syntax and git diff whitespace checks: passed.

### Browser role matrix actually exercised

| Synthetic user | Grants used | Browser checks passed |
| --- | --- | --- |
| asset-viewer | it_assets.view | Asset list/detail/categories/reports, independent navigation/card, hidden mutation controls, all 17 forged POST denials |
| helpdesk-viewer | helpdesk.view | Ticket list/detail/reports, independent navigation/card, hidden mutation controls, all 17 forged POST denials |
| it-manager | all four IT permissions | Management links/forms, asset assign/return, ticket assignment/start/resolution, all 17 routes reject missing/invalid CSRF |
| super-admin | all four IT permissions | Management links/forms, asset assign/return, ticket assignment/closure, all 17 routes reject missing/invalid CSRF |

The browser runner uses separate Chrome browser contexts and real login forms.
It checks business/history/audit snapshots around rejected operations. Revoking
only management grants in the disposable DB causes all 17 requests from the
existing manager session to be denied, while read views remain accessible and
buttons disappear. Disabling that synthetic account rejects its next POST/GET.
Existing Chrome login validation, two-tab session/cookie, CSRF-expiry recovery,
logout and stale-tab checks also pass. HTTP integration separately exercises all
17 successful mutation routes and both report export endpoints.

The Super Admin browser fixture intentionally isolates the four relevant IT
grants. Broader administration/audit paths are covered by the existing regression
suites; the fixture does not claim to reproduce every production role grant.

### Browser infrastructure diagnosis and reproduction

The original command sandbox prevents Chrome child processes from starting
normally. A minimal `about:blank` diagnostic, independent of ERP, produced repeated
GPU child-process exits `0xC0000022` (access denied), followed by fatal
"GPU process isn't usable. Goodbye.", Chrome exit `0x80000003` and DevTools
WebSocket close 1006/ECONNRESET. A software/in-process GPU experiment kept the
browser alive but still timed out enabling the renderer (`Page.enable`).

Running the verified disposable runner outside the command sandbox resolved the
child-process restriction. The passing run restored the original Chrome flags;
no `--no-sandbox`, disabled web security, CSRF exemptions, cached authorization,
role-name bypass or application security changes were introduced. Do not add
browser security bypasses to work around this infrastructure restriction. Run the
browser test in an execution environment that permits normal Chrome child
processes. Test-only fixture/control endpoints exist only inside the disposable
runner; the fixed synthetic revocation/disable controls additionally require its
random per-run key and genuine CSRF token.

Reproduce using `python -B tests/mysql_security_review.py` from the project's
virtual environment, with normal Chrome child-process access. The harness checks
its temporary MySQL datadir and shuts down its server/browser afterwards.

### Remaining manual browser checks

Use a separately provisioned disposable acceptance instance with synthetic users
and the same four role/grant combinations above. Never use company records.

1. At 1440px and 390px widths, inspect dashboard, asset/ticket lists, detail pages,
   categories and reports with the intended CSS available. Check clipping,
   spacing, blank action areas, scrolling and horizontal menus. Use Tab, arrows
   and Escape to check visible focus and menu dismissal. The headless run blocks
   external HTTPS resources, so it does not certify Bootstrap/CDN visual rendering.
2. With IT Manager/Super Admin, submit through the actual visible buttons/forms:
   category add/edit/status; asset add/edit/assign/return; maintenance add/complete;
   lost/restore and retire/restore on separate unassigned fixtures; ticket
   create/assign/start/resolve/close. Confirm status/history after each click.
   All 17 backend operations were integration-tested, but the browser automation
   uses same-origin fetch for mutations and does not click every native form.
3. As the appropriate viewer, click Asset and Help Desk report exports. Confirm
   the browser download completes, filenames are sensible, and saved workbooks
   open with the synthetic data. HTTP export access passed; browser file saving
   and spreadsheet application behavior were not automated.
4. If deployment acceptance requires it, separately verify production HTTPS/TLS,
   Secure cookie behavior, proxy/CDN availability and browser console errors on a
   non-company acceptance deployment. Loopback testing does not certify hosting.

No commits, pushes, merges or branch switches were performed. Custom-role grants
and ticket ownership/assignee restrictions remain the previously documented policy
decisions; they do not prevent a review checkpoint for the scoped Step 1 change.
