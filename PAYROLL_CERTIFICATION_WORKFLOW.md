# Payroll Step 5B.3B — certification workflow and source coordination

Starting checkpoint: clean `fix/payroll-reliability` at `b24cf9f`. This change adds
preparation/review, controlled publication/corrections/revocation infrastructure,
and Employee/Compensation source coordination. No salary formula, calculation
evidence version 2, entry-generation eligibility, submission, approval or payment
cutover is implemented. Historical Payroll snapshots and PAID values are retained.

## Production publication is unavailable

The ERP has no approved authoritative payroll-population source, historical
employment/rate coverage source, approved holiday/schedule registry, or formal
company certifier mapping. `authoritative_evidence()` therefore returns None.
The production repository refuses publication even when every database field is
populated and the actor has the certification permission. There is no environment
flag, testing-mode bypass, submitted checkbox or application setting that enables
publication. The UI disables publication and explains the dependency; forged POSTs
remain subject to the same backend check.

Disposable tests explicitly patch this boundary with captured synthetic expected
claims and certifier identities. Those fixtures are not deployed adapters and
do not certify company rules. A future approved adapter must independently supply
the entire expected roster, authoritative source/version references, calendar and
employee evidence, and authorized certifiers for the exact cutoff. Matching a
reference string alone does not authenticate a document.

The following approvals/sources remain necessary before real publication:

- An authoritative, versioned cutoff roster and a completeness basis, including
  historical/inactive staff and justified exclusions, not just current Active staff.
- Employment coverage/separation evidence and applicable compensation coverage.
  One editable compensation row and current employment status cannot prove history.
- An approved calendar/version, holidays/special days and employee schedule facts.
- Formal certifier/revoker authority and explicit reviewed role grants.

No new company policy on self-certification, proration, statutory calculations,
odd-cent allocation, excess deductions or historical correction was introduced.

## Repository and preparation contract

`payroll_certification_repository.py` provides period revision listing, detail
review, initial assembly preparation, declared-roster editing, individual member
evidence preparation, publication, corrected replacement preparation, revocation
and current-certification review. No certification is created automatically by
period generation.

Preparation requires a DRAFT, policy-pinned period with exact A/B dates. The policy
must be APPROVED and activated, pass its configuration seal and cover the entire
cutoff. The submitted employee population must be explicit, unique, existent and
within schema limits. Every included/excluded employee eventually needs a member
record. Current employment status is never an automatic eligibility decision.

Hire/status and compensation identity/rate/type/currency/effective date are read
from ERP and displayed for review. Full-cutoff employment and compensation end
coverage/supporting references are separate prepared claims. Missing history is
left missing. EXCLUDE needs a reason/reference and never asserts that no historical
pay is owed. An inactive employee with known hire date can be included only if
authoritative full-cutoff evidence is available; unknown or mid-cutoff hire dates,
missing compensation and unsupported pay types cannot pass publication.

Scheduled dates are derived from the pinned Monday-Friday template using safe
inclusive date iteration. This is a proposed date set, not calendar attestation.
Known holiday/special-pay/schedule exceptions can be recorded as structured fields
in assemblies; they block publication. The first supported publication requires
complete expected dates and no unsupported exceptions confirmed by an approved
source. No holiday/overtime formula or automatic leave entitlement is inferred.

All references/dates/identifiers are validated before DML. Monetary snapshots use
the existing exact Decimal validator. Unknown/repeated fields, stale assemblies,
missing employees and malformed exception groups are rejected. Preparation and
member forms retain submitted values on validation errors. A member source token
requires reloading if ERP facts changed since the form opened, preventing silent
rate adoption. Payroll entry compensation snapshots are never refreshed.

Unsealed draft concurrency uses a deterministic token over header, member and
event content because 006's revision is a published-chain version, not an edit
counter. Member identity changes, source changes and events cannot silently
overwrite a stale form. Replacements require the exact latest predecessor and
current predecessor token, explicit correction reason/reference and fresh member
review; sealed history is not edited or copied into automatic eligibility.

Review compares current material sources with captured digests, labels stale
evidence and shows recorded snapshot details and field-level revision differences.
Names/contact/notes are not material hashes. The population digest includes all
ERP employee IDs to conservatively detect new unreviewed employees. These digests
compare current facts, not a complete immutable master-data change history; they
do not replace external source revocation/approval checks. A fact reverted exactly
to its original value can match again, while explicit certification revocation
remains permanent history.

Current-certification review selects the highest SEALED revision first, then
reports its terminal events and source consistency. It never selects the highest
unrevoked older revision. An ASSEMBLY replacement does not itself supersede the
prior seal. Source consistency is not production authorization.

## Publication, correction and revocation transactions

Every certification write starts a transaction and acquires Payroll guard row 1
before material locks. It locks/revalidates the period, activation/policy coverage,
revision/members and source rows, then performs business writes and commits once.
The guard serializes participating writers; all comparisons are repeated inside
the transaction. SQL errors and lock conflicts roll back; uncertain commit errors
are not retried automatically and the UI directs operators to check history.

Publication validates exact membership, per-member source fingerprints, known
full-cutoff hire/coverage, supported MONTHLY/PHP compensation, schedule/calendar,
and independent authoritative expected claims/certifier identity before sealing.
Arbitrary nonempty references or VERIFIED dropdown selections are insufficient.

Migration 006 generates required CERTIFY/SUPERSEDE business events atomically with
the seal. Migration 007 preserves supplied correction reason/reference in the
SUPERSEDE event. Concurrent publications produce one seal, not duplicate success
events; concurrent corrections cannot branch a predecessor.

Revocation appends REVOKE with the authenticated actor, reason and reference.
Duplicate/terminal transitions are rejected; older revisions are not reactivated.
Withdrawal does not require the supporting policy/calendar still to be valid.
Revocation can record a problem without reopening or updating APPROVED/PAID
financial records. Required event failures roll back the associated operation.

The application never inserts calculation evidence version 2 and never adds new
financial-finalization gates in this checkpoint. A real old manual period still
calculates, submits, approves and pays under matching version-1 evidence after
004-007; compensation edits preserve its original entry snapshot.

## Cross-module source coordination

Employee creation and material hire/status updates acquire the guard before any
business write lock. Compensation creation and pay-type/rate/effective-date
changes do likewise. Unlocked classification probes are ended with rollback before
the coordinated write transaction starts; no source lock is carried into a guard
wait. Profile-only Employee updates write only profile columns, preserving a
concurrent eligibility change. Compensation notes-only updates write only notes
and actor. Those paths avoid unnecessary global guard acquisition.

Certification lock order is guard, period, activation/policy, certification/member
rows, then material Employee/Compensation rows. Material source writers use guard
then their source rows. All participating guarded writers serialize first; existing
Attendance/Leave locking is unchanged. Source changes make review/publication
stale by content comparison; they do not rewrite sealed evidence or Payroll data.

Direct SQL, imports and mixed old workers that bypass the guard cannot provide
these guarantees. External evidence may change without any ERP row change; an
approved source adapter must also verify its live authority/revocation state.

## Authorization and Audit Logs

Reads use `payroll.view`; preparation/member editing/corrections use
`payroll.process`; publication uses `payroll.certification.certify`; revocation
uses `payroll.certification.revoke`. Existing per-request authorization,
disabled-account checks and global CSRF remain authoritative. Horizontal navigation
is retained, with a Certification link from Payroll period details. Controls follow
permissions and state, independently of backend enforcement.

`database/payroll_certification_permissions.sql` is explicit repeatable catalog
registration only. It does not grant any role, run at startup or add a Super Admin
bypass. Company role mappings remain unapproved. Tests explicitly grant synthetic
roles in newly initialized databases only.

Successful CERTIFY, SUPERSEDE and REVOKE actions use central Audit Logs after the
business commit. Events include actor, numeric certification identity, period and
revision. SUPERSEDE identifies the predecessor and replacement. Prepared payloads,
rates, personal documents and supporting-reference contents are not copied into
central descriptions. Failed validation/rollback/denial/CSRF and duplicate actions
produce no success audit.

Required certification business events are transactional and mandatory. Central
Audit Logs remain best effort: SQL audit outages do not undo publication,
supersession or revocation. A committed operation can therefore lack a central
audit row; this is the preserved existing model.

## Migration 007 and deployment

The user explicitly approved an additive migration after review identified that
006's fixed SUPERSEDE reason could not retain a supplied correction explanation.
`007_payroll_correction_references.py` adds nullable `correction_reason` and
`correction_reference`, validates their pair, requires them for new replacements
and replacement seals, and updates the known seal-event trigger. Existing SEALED
006 rows retain NULL fields and unchanged digests/events. No backfill or permission
grant is performed. Legacy unsealed replacements can receive the fields through
the normal assembly edit form; sealed history remains immutable.

007 preflights compatible 004-006 metadata, owned columns/checks and known trigger
bodies/modes; it rejects incompatible objects and incomplete 006 prerequisites.
It takes migration locks for 006 and 007, uses strict migration-session mode and
restores it. Only the known old seal trigger is replaced; interrupted replacement
with that trigger absent resumes. Missing compatible additive fields/checks/new
triggers can resume. No application code invokes migrations or reads credentials.

Use explicit CLI target arguments and a password prompt only through a separately
approved controlled database upgrade. No actual database upgrade was performed:

```powershell
.venv\Scripts\python.exe database/migrations/007_payroll_correction_references.py --host HOST --port 3306 --user MIGRATION_USER --database DATABASE
```

Verify backup/restore, MySQL prerequisites, exact target, trigger DEFINER privileges
and full 006 completion. Pause certification/Payroll/HR writes across every worker
before DDL and coordinated deployment. MySQL DDL implicitly commits; DROP/CREATE
trigger replacement has an interruption gap that must never be exposed to live
certification writers. Retain sibling migrations 005/006 for metadata verification.
After 007, rerun 007 to verify the extended contract; the unchanged historical 006
manifest intentionally does not accept the added columns/trigger definition.

Register the permission catalog through approved upgrade procedures, then review
any role grants separately. Deploy all participating source writers together.
Keep real publication unavailable until its authoritative-source integration and
company authority are approved. Rollback must retain evidence; do not drop history
or roll back to uncoordinated writers while allowing certification publication.

## Verification

Full Python: 322 passed. JavaScript: 11 passed. All 24 existing disposable MySQL
smoke suites passed, plus the new workflow suite (25 total). The new suite uses
004-007, synthetic records and explicit grants. It verifies missing/mid-cutoff
hires, historical exclusions, incomplete/authoritative-roster mismatch, coverage,
pay types, unsupported calendar/schedule conditions, source-token rejection,
business-event/late-member rollback, central audit outages for all three actions,
007 legacy seal preservation/repeat/recovery, exact audit actors/IDs and unchanged
version-1 snapshot/payment behavior.

Four actual two-writer InnoDB races observe both guard waiters before release:
duplicate publication, competing correction preparation, Employee source versus
publication, and Compensation source versus publication. Nonmaterial profile/
notes updates complete while the guard is held. Old Payroll freshness/monetary,
Finance, Procurement, receiving, Inventory, IT/Help Desk, security and audit smoke
suites passed. The new paths also verify forged POST denial, fresh permission
revocation, disabled users and CSRF.

Real Chrome 155.0.8059.80 verifies native preparation, retained validation errors,
explicit exclusions, reviewed ERP facts, view-only restrictions, forged publication,
CSRF and the production source blocker. Synthetic successful publication,
supersession and revocation are tested through real Flask routes/MySQL, not native
Chrome actions. Existing Chrome Payroll/policy, IT and cross-module security
workflows pass. Production TLS and fully styled desktop/mobile review remain
manual checks. No production performance claim is made.
Compilation passed for 117 Python files and 114 Jinja templates; dependency,
JavaScript syntax and diff checks passed. No company databases were accessed.

## File manifest

- Application: `app.py`, `payroll_certification_repository.py`,
  `employee_repository.py`, `payroll_repository.py`.
- Database: migration 007, `database/payroll_certification_permissions.sql`,
  `database/migrations/README.md`.
- UI: `templates/payroll/periods/view.html` and five certification templates:
  index, prepare, member, detail and exception fields.
- Tests: `tests/test_payroll_certifications.py`,
  `tests/mysql_payroll_certification_workflow_smoke.py`,
  `tests/browser_payroll_certifications.cjs`, `tests/browser_security_review.cjs`,
  `tests/mysql_security_review.py`, `tests/payroll_schema_helpers.py`,
  `tests/test_csrf_security.py`.
- Documentation: this file.

Ready for Step 5B.3B review with real publication explicitly unavailable. No commit,
push, merge, reset or branch switch is part of this task. Wait for review before
Step 5B.3C.
