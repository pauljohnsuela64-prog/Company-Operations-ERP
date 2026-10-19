# Employee/Department validation and write integrity (Step 2B)

## Scope and compatibility

`hr_validation.py` validates Employee and Department writes at both route and
repository boundaries against `database/core_schema.sql`. Optional fields remain
optional. Employee numbers and department codes are trimmed and uppercased,
including a length check after Unicode case expansion. Hire dates must be real
calendar dates within MySQL DATE range; no hire-date eligibility policy is added.
Creation still sets Active. Editing accepts the existing five employment statuses.

Routes retain raw submitted form values on validation/integrity errors. Invalid
department selections remain visible and are rejected again until corrected;
they do not silently become No Department. Expected duplicates, invalid
references, lock timeouts and deadlocks use concise validation messages. Unknown
database/programming failures are rolled back and re-raised, not hidden.

No schema migration, role grant, employment history, user-account deactivation or
Payroll rule change is included. Existing references are not moved or repaired.
Central HR business-action auditing remains future work; this checkpoint adds no
success audit events or false success messages for rejected writes.

## Transactions and lock order

- Employee creation locks the selected department `FOR SHARE` before INSERT.
- Employee editing locks the existing employee `FOR UPDATE`, then the selected
  department `FOR SHARE`, and writes on the same connection/transaction.
- A different inactive department and nonexistent department are rejected. An
  existing inactive association may be retained, based on the locked current row.
- Department edits/status changes lock the department `FOR UPDATE`. They do not
  subsequently acquire employee or asset locks. This respects IT Asset's order
  of asset, employee, category, department; HR never acquires asset locks.
- Deactivation that commits first prevents a new assignment. Assignment that
  locks first may commit, followed by deactivation. This does not prohibit a
  department from becoming inactive while employees remain associated with it.
- Updates return False for missing records and True for existing records,
  including valid no-op updates. SQL/commit failures roll back and close resources.

Department status POSTs now require explicit `is_active=0` or `is_active=1`.
Repeating the same request is idempotent. Old cached forms and external callers
that omit this field receive a validation message and must reload/update; there
is no fallback to toggling. Opposing explicit requests still use last commit wins.

## Deferred risks and Step 2C

Step 2B alone did not protect stale Employee or Department forms. Step 2C.2 now
adds the separately reviewed revision contract described in [HR_REVISIONS.md](HR_REVISIONS.md).
Deploy that application change only after explicitly completing migration 008.

Employment status remains independent of login account activation, Attendance and
Leave eligibility, and IT Asset custody. Offboarding, employment history,
separation/rehire and historical department attribution require company policy
decisions. No inferred policy or automatic historical correction is implemented.

## Reproducible verification

Use only synthetic records and the disposable test launchers:

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
.venv/Scripts/python.exe -B tests/mysql_hr_validation_smoke.py
.venv/Scripts/python.exe -B tests/mysql_hr_validation_browser.py
```

The MySQL suite verifies strict/non-strict modes, field boundaries, duplicates,
missing targets, observed real lock waits in both eligibility orders, rollback,
repeated/concurrent desired states, permissions, CSRF and retained historical
references. The browser runner composes native HR forms with existing security
checks against a disposable server and temporary Chrome profile. A failed Chrome
DevTools connection is not an application workflow pass; report it separately.

Manual checks when Chrome automation is unavailable: create/edit both record
types; forge overlong text and invalid references; confirm messages and all form
values survive; correct and resubmit; keep an existing inactive department on an
unrelated edit; repeat explicit status requests; verify viewer controls and forged
POST denial. Check desktop/mobile layout separately from functional automation.
