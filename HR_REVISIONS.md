# HR revision contract (Step 2C.2)

Employees and Departments use signed `BIGINT NOT NULL DEFAULT 1` revisions and
enforced named `CHECK (revision >= 1)` constraints. Existing rows start at 1 as a
concurrency baseline, not a reconstructed history of earlier changes. Repeated
upgrades do not reset counters. MySQL 8.0.16+ and InnoDB are required.

## Standalone migration 008

`database/migrations/008_hr_employee_department_revisions.py` follows the existing
explicit `upgrade(connection)`/CLI convention. There is no sequential migration
runner. It neither imports nor requires the paused Payroll migrations 004-007.
The numbering gap is intentional; merging those branches later must preserve
both independent migration sets and recheck compatibility, not apply Payroll as
an HR prerequisite. This change contains no Payroll modifications.

The upgrade preflights both tables, expected column types/nullability, business
defaults, primary/unique keys, timestamps, InnoDB and the Employee Department FK.
Existing revision columns and named constraints must have compatible definitions;
unexpected revision CHECKs and unenforced constraints require manual review.
All preflight checks run before ALTER statements. The upgrade never reads `.env`,
connects on import or runs during application startup.

Only an approved operator, after backing up and pausing/draining all HR writers,
should run this against an explicitly selected database:

```powershell
.venv/Scripts/python.exe database/migrations/008_hr_employee_department_revisions.py --host HOST --port 3306 --user MIGRATION_USER --database DATABASE
```

The password is prompted. Do not put credentials in commands or committed files.
DDL implicitly commits and may wait for metadata locks or rebuild a table. Size
the maintenance window using representative data; no production-scale timing is
claimed. Each completed ALTER persists independently. After interruption, rerun
the upgrade to validate/complete missing columns or CHECKs; never reset revisions.
Fresh installations use the matching `core_schema.sql` definitions.

Deploy only after BOTH tables verify successfully. All workers and external
callers must use the revision-aware contract before writes resume. Old cached
forms without a revision fail closed and require reload. Mixed old/new writers
are unsafe. Prefer fix-forward or retaining additive columns during rollback;
do not reopen writes through old code while claiming stale-edit protection.

## Write semantics

- `update_employee`, `update_department` and `set_department_active_status`
  require keyword-only `expected_revision`; no fallback fetches a current token.
- Employee editing locks Employee `FOR UPDATE` before Department `FOR SHARE`,
  validates current eligibility, and conditionally writes by ID and revision.
  HR takes no asset locks, preserving IT's asset/employee/category/department order.
- Department edits/status requests lock Department `FOR UPDATE` and acquire no
  Employee/Asset locks afterward. Assignments alone do not increment Departments.
- Every successful detail save consumes one revision, including an unchanged
  visible payload. A retry of that consumed token is stale. Success returns
  `HRWriteResult(revision=<new integer>, changed=True)` only after commit.
- Status requests with current revision and a different desired state increment
  once. Current/older revisions requesting the already-current state return
  `changed=False` and the current revision, without UPDATE. Future revisions are
  rejected before this no-op exception. Opposing stale requests return conflict.
- Malformed/missing/out-of-range tokens yield HTTP 400; stale/future tokens yield
  409; missing targets yield 404 on POST; exhausted counters yield 503 for writes
  requiring increments. Same-state status no-ops remain possible at exhaustion.
- Signed BIGINT exhaustion is checked before arithmetic, with a conditional SQL
  upper bound too. Never wrap, clamp, reset or silently retry using a fresh token.
- SQL, validation and commit failures roll back fields and revisions. Duplicate
  identifiers retain ordinary validation behavior. Unknown errors are re-raised.

## Forms and security

GETs render a decimal-string revision. All POST validation redisplays preserve
the original submitted revision, even if the loaded record is now newer. Conflict
pages return 409, escape submitted values for comparison, offer a reload link,
and contain no Save form or refreshed revision. Nothing auto-merges or resubmits.
Status no-ops use an informational message, not a claim that a new change occurred.

Revisions are concurrency evidence, not authorization credentials. An authorized
editor can deliberately load and submit a current revision; counters do not
authenticate intent. Existing permissions, per-request authorization, disabled
account checks and global CSRF remain the security boundary. No new HR business
audit events, role grants, user deactivation or employment/Payroll policies are
introduced.

## External-writer limitations

Administrative SQL, imports, restores and future writers must participate in the
counter contract. `ON DELETE SET NULL` can change Employee department references
without advancing revisions; MySQL FK cascades do not activate ordinary row
triggers either. There is no new Department/Employee deletion workflow or trigger
here. Inventory external writers before deployment; unmanaged writes, identity
reuse and restoring older counters invalidate application-only guarantees.

Attendance, Leave, asset custody/history and User associations are not rewritten.
Employment status remains independent of account activation and entitlement.

## Verification

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
.venv/Scripts/python.exe -B tests/mysql_hr_revision_smoke.py
.venv/Scripts/python.exe -B tests/mysql_hr_validation_smoke.py
.venv/Scripts/python.exe -B tests/mysql_hr_validation_browser.py
```

These launchers use synthetic records and verified disposable MySQL only. Coverage
includes strict/non-strict modes, fresh/legacy/partial migration states, incompatible
schema rejection, exactly-one-commit races, observed InnoDB lock waits, rollback,
BIGINT limits, retained tokens and Chrome independent-tab conflict/reload flows.
Desktop/mobile appearance and production HTTPS require separate manual checks.
