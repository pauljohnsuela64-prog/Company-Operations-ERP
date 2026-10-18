# IT Asset Step 2: master-data validation and transaction reliability

Base: clean `261c152`, branch `fix/it-asset-lifecycle`. No migration, dependency,
permission/role grant, central IT audit integration or GUI redesign is introduced.

## Validation boundaries

`it_asset_validation.py` owns the repository input boundaries. Routes pass form
values to repositories rather than converting monetary input through floats or
relying on MySQL coercion. Direct repository callers receive the same validation.

| Field | Boundary |
| --- | --- |
| Asset tag | Required, uppercase, at most 50 characters after uppercasing |
| Asset name | Required, at most 150 characters |
| Brand/model/serial number | Optional, at most 100 characters each |
| Asset and maintenance notes | Optional, at most 255 characters |
| Maintenance type | Required text, at most 50 characters; existing VARCHAR/custom-type semantics retained |
| Maintenance description | Required, at most 255 characters |
| Maintenance vendor | Optional, at most 150 characters |
| Purchase/maintenance cost | Optional Decimal, zero allowed, maximum 9,999,999,999.99 (DECIMAL(12,2)) |
| Identifiers | Positive signed INT, maximum 2,147,483,647; supported optional references may be blank |
| Dates | Real ISO calendar dates within MySQL DATE range 1000-01-01 through 9999-12-31 |
| Condition | NEW, GOOD, FAIR, POOR or DAMAGED |

Costs reject NaN/Infinity, floats, negative input, exponential notation, malformed
grouping, more than two decimal places and overflow. Correctly grouped thousands
remain supported. No silent rounding/truncation occurs, including with non-strict
SQL mode. Blank optional costs become NULL; zero remains visible as zero on Edit.
Initial AVAILABLE/ASSIGNED states must agree with whether an employee is supplied.

Maintenance completion requires a valid stored start date and completion date on
or after start, including same-day completion. Invalid legacy start dates reject
with feedback rather than causing a Python comparison error. No future-date ban,
purchase/maintenance ordering or warranty-versus-purchase ordering is invented.
Used equipment may have an expired warranty when purchased; further chronology
restrictions require an explicit business decision.

## References, locking and historical compatibility

Newly selected asset categories/departments must exist and have is_active=1,
matching existing Add/Edit option lists. An unchanged category/department link may
remain inactive on Edit; the current historical record is included in the form.
Changing to a different inactive reference rejects. Edits do not rewrite previous
custody history or change current employee/lifecycle status.

Employees must exist. The current ERP selects employees of every employment
status, so Inactive/Resigned/Terminated assignment remains compatible pending an
approved eligibility policy. Employee employment_status is a VARCHAR, not an
active flag. New restrictions are not inferred from the status label.

Existing-asset writes retain asset-first FOR UPDATE locking. Create/edit reference
checks use FOR SHARE under the same write transaction, in employee (if applicable),
category, department order. Initial creation has no existing asset to lock; it
checks masters before inserting the new asset and its initial history atomically.
Concurrent deactivation/deletion either waits for a valid write to commit or is
observed by its locking read before the write proceeds. Failed checks roll back.

Assignment also validates/locks the employee and supplied department inside the
asset transaction before creating custody. It preserves the existing independent
asset-department semantics: the route supplies the employee department it read,
and the repository does not impose a new equality rule against an employee's
subsequently changed department. The referenced department must exist, but an
inactive department reached through this existing assignment workflow is not
newly prohibited. Review department ownership/synchronization separately.

Unique asset-tag/serial-number constraints remain authoritative, including
concurrent duplicate registrations. Duplicate keys become clear ValueError
messages after rollback; lock timeouts/deadlocks and foreign-key races receive
reload/retry or missing-reference feedback. Other unexpected database failures
propagate for operational diagnosis after rollback. No uncertain COMMIT is retried
automatically and no extra success flash/audit is emitted after failure.

## Form reliability and security

Shared asset form handling redisplays submitted text, dates, cost, category,
department, employee and condition selections on failed Add/Edit submissions.
Saved values are used only on the initial Edit GET; explicit clears remain clear.
Unavailable/malformed references are rendered as escaped selected placeholders
with visible feedback, so they cannot silently become another record or None.
Maintenance Add similarly retains all its submitted fields and type selection.
Browsers may display invalid numeric/date strings as blank native controls, but
the server response retains the submitted value and explains the validation error.

Maintenance completion retains its existing redirect/error-feedback behavior;
invalid completion dates do not alter the maintenance record or asset. Its inline
completion input is not restored through that redirect.

All existing it_assets.view/manage, Help Desk permissions, global CSRF, fresh
authorization and role-based controls remain. No new route or audit behavior is
added. Approved LOST/MAINTENANCE return blocks, normal returns, retirement,
recovery/completion without prior returns and stale assignment-ID checks remain
unchanged; the twelve lifecycle race regressions still pass.

## Results and reproduction

- Full Python suite: **248 passed** (including seven new validation tests).
- JavaScript navigation suite: **11 passed**; all CJS syntax checks passed.
- **12 disposable MySQL suites**: new IT validation, IT lifecycle, IT Authorization/
  Help Desk, four Finance suites, Procurement, stock, receiving, security and
  central audit passed. No configured ERP/company database was accessed.
- New MySQL validation coverage uses non-strict SQL mode: schema boundaries,
  malformed/overflow inputs, duplicate create/edit, raw form retention, inactive
  historical references, inactive employee compatibility and assignment history.
- Four actual master-lock waits prove concurrent category/department deactivation
  rejects stale create/edit references. A fifth observed wait proves a concurrently
  deleted employee cannot acquire an assignment. Simultaneous duplicate registration
  commits exactly one asset/history pair.
- Actual late history INSERT, maintenance asset UPDATE, completion asset UPDATE
  and injected pre-COMMIT failures prove asset/history/maintenance rollback.
- Chrome passed native Add/Edit/maintenance failed validation and correction,
  duplicate feedback, zero-cost display, completion chronology and legitimate
  return afterward. Existing viewer/manager/Super Admin, CSRF, revocation, disabled
  account, Help Desk and approved return-policy browser checks passed too.
- Python/Jinja compilation, dependencies and whitespace checks passed. An AST scope
  review found only IT asset Add/Edit/maintenance routes and their shared form helper
  changed in app.py; Finance, Procurement, Inventory and authorization helpers did not.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
.\.venv\Scripts\python.exe -B tests/mysql_it_asset_validation_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_it_asset_lifecycle_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_it_authorization_smoke.py
.\.venv\Scripts\python.exe -B tests/mysql_security_review.py
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Chrome runs with unchanged security flags outside the command sandbox whose
DevTools connection was previously reset. Test helpers, profiles and MySQL data
are disposable; external HTTPS assets are blocked.

## Compatibility, policy decisions and remaining risks

No database migration is required. Existing MySQL 8.0/InnoDB tables, unique keys,
foreign keys, VARCHAR/DATE/DECIMAL definitions remain prerequisites; checked-in
schemas rely on the server's default engine. Actual company schemas/data were not
queried or changed. No legacy data or assignment history was repaired/backfilled.
Stricter input checks can reject values formerly coerced by non-strict SQL and
direct repository callers passing floats. Invalid historical data needs review.

Policy decisions remain: employee employment-status eligibility; assignment through
inactive employee departments; department ownership synchronization; warranty/
purchase/future-date rules; and an approved legacy repair process. None blocks
the narrow implemented validations or changes the approved lifecycle return policy.

Legacy contradictory states/history still fail closed and require reviewed repair.
Metadata edits still use last-writer-wins semantics; no new optimistic edit/version
policy is added. Direct SQL can bypass application checks, unrelated writers can
still cause deadlocks, and unknown commit outcomes require operational review.
Central IT auditing was deferred at Step 2. Step 3 now integrates postcommit
business-action events; see [IT_ASSET_AUDIT.md](IT_ASSET_AUDIT.md).

Manual acceptance should cover styled desktop/mobile forms and long validation
feedback, inactive historical choices, native date/number control behavior, inline
completion errors/retry and HTTPS/Secure-cookie deployment. External Bootstrap CSS
is blocked in automation, so full visual acceptance is incomplete. No production-
scale performance claim is made.

Await review before Step 3. No commit, push, merge or branch change performed.


## Step 5A: category validation correction

Baseline: `fix/it-asset-lifecycle` at `21adc0d`. Category Add/Edit previously relied
on HTML maxlength for their VARCHAR limits. Forged oversized input could produce
MySQL error 1406 in strict mode or silently truncate and audit a successful write
in non-strict mode.

Both routes now share a category form handler and `category_values()` from the
existing validation module. The category repositories also validate before opening
a connection. Code/name are required; normalized code/name/description have maximum
lengths 30/100/255. Whitespace is stripped for persistence, codes are uppercased,
and uppercase Unicode expansion is checked against the code limit. An empty
optional description remains SQL NULL. Category names remain non-unique; only
category codes are unique in the existing schema. No new business rule is added.

Validation and duplicate-code failures render the same Add/Edit page with all
submitted values retained and HTML-escaped, including oversized text for correction.
There is no redirect that discards rejected Edit values. Validation runs before SQL;
existing write transactions/rollback and activation/deactivation are unchanged.
Successful changed records retain exactly one central CREATE/UPDATE event after
commit. Invalid, duplicate, denied and rolled-back writes emit no success event;
the central best-effort audit failure boundary remains unchanged.

Regression coverage is in `tests/test_it_asset_category_validation.py`,
`tests/mysql_it_asset_category_validation_smoke.py`, and
`tests/browser_it_asset_categories.cjs` (called by the existing browser harness).
The new MySQL suite explicitly sets and verifies strict and non-strict session
modes, tests exact boundaries and overflow on CREATE/UPDATE, missing fields, raw
form retention/escaping, Unicode normalization, optional descriptions, duplicate
codes, unchanged database/audit snapshots, real UPDATE rollback, activation,
CSRF and fresh permission revocation. Direct repository invalid input is also
rejected before SQL. All database records are synthetic and disposable.

No schema/migration, role grant, lifecycle/return policy, historical repair or
unrelated module change is required. Existing manual visual acceptance,
production TLS, best-effort audit durability, legacy reconciliation and export
scaling limitations remain as documented in the prior IT steps.

Step 5A final verification: 267 Python tests, 11 JavaScript tests and seventeen
disposable MySQL suites passed, including the new dual-mode category suite and
existing IT lifecycle/validation/audit/reporting/authorization, Finance,
Inventory, Procurement, receiving, security and central Audit Logs suites.
Chrome native category Add/Edit passed all three overflow/retry cases, duplicate
retention and activation/deactivation alongside existing IT/security workflows.
Compilation passed for 88 Python sources, 104 Jinja templates and six CJS scripts;
dependency and diff checks passed. Styled visual acceptance and production TLS
remain manual checks. Changes are ready for review before an authorized Git
checkpoint or Pull Request; no commit, push or branch change was performed.
