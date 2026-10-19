# Payroll 5B.5B: synthetic whole-period transaction integration

Development/test infrastructure only. The pure monthly prototype, production
calculation/entry generation/submission/approval/payment routes and their business
policies remain unchanged. Nothing authorizes real payroll calculations,
certification publication, legacy-v1 payment restrictions or production deployment.
No migration or production role grant is added.

## Transaction ownership

`payroll_evidence_repository.persist_proposed_in_transaction(cursor, period_id,
entry_id, outputs, actor_id)` uses an existing active transaction. It opens no
connection, never commits/rolls back, and reuses the existing authoritative
eligibility/source, monetary, ownership and canonical-evidence validation. It
inserts one append-only evidence row and changes outputs/version/hash/current
pointer in ONE entry UPDATE. It returns the new numeric evidence ID.

The caller must acquire the shared guard BEFORE other locks, and must roll back
the ENTIRE transaction on any exception. Catching an error and committing earlier
entries is a caller bug. An active explicit transaction is sufficient even when
the session default is autocommit=1; an inactive transaction is rejected before
business SQL. The existing `persist_proposed()` wrapper still opens one connection,
starts one transaction, invokes persistence, commits once, or rolls back on error.
Its existing valid-input/public behavior and audit boundaries remain intact.

No change is made to `payroll_freshness.py` or `payroll_evidence.py`: version-1
projection/serialization/hashes and version-2 canonical serialization remain exact.
The new helpers do not change any production finalization version dispatch.

## Bounded synthetic adapter

`tests/payroll_synthetic_period.py` is a test harness, not a production repository,
Flask route, CLI, worker or scheduler. It has no configured connection factory,
authority override, environment enable flag, network fetch or audit writer.
Production modules do not import it.

The smoke launcher starts a fresh loopback MySQL server and verifies its temporary
datadir before creating records. The adapter checks the connection is loopback,
the datadir matches the explicit local `erp_audit_smoke_*/data` fixture, and the
database is exactly `erp_synthetic_payroll_period` BEFORE business writes. It has
no way to obtain ordinary application database settings on its own.

The fixture supplies explicit immutable hypothetical calculator inputs and expected
entry markers (entry ID, status, evidence version/hash/pointer). The isolated smoke
process, outside the adapter, uses a scoped unittest mock of
`authoritative_evidence` with captured synthetic claims. Production still returns
None and fails closed. No bypass parameter or synthetic authority branch is added
to any real validator. The adapter without that scoped source fixture fails.

One run:

1. Verifies database metadata isolation, ends that metadata transaction, then
   starts the business transaction and acquires the guard first.
2. Uses the real eligibility validator to lock the period, resolve the original
   approved/activated policy and latest valid certification, and lock deterministic
   employee/compensation and entry populations.
3. Requires Draft status, unchanged entry markers, the explicitly hypothetical
   policy profile and the exact included synthetic roster.
4. Transactionally invalidates existing Draft v2 associations/outputs.
5. In entry-ID order, invokes the unchanged pure prototype, validates all outputs,
   builds real v2 source evidence and checks fixture dates/rates/coverage/references,
   attendance, approved daily leave and adjustments against locked database facts.
6. Calls cursor-owned persistence for every entry, then commits ONCE. Any later
   employee/failure rolls back all preceding writes and invalidations.

The database policy's existing bounded engine vocabulary and the pure prototype's
explicitly hypothetical engine are translated ONLY in this disposable harness.
Synthetic evidence in this test database must not be exported/imported as approved
production evidence. No real HR evidence or policy approval is claimed.

Competing/repeated requests with the same reviewed markers cannot silently create
duplicate evidence: after one commit, the other rejects changed pointers. A
deliberate recalculation needs newly reviewed fixture markers and appends a new
per-entry sequence while retaining earlier evidence.

## Draft invalidation

`invalidate_period_in_transaction(cursor, period_id)` requires an active caller
transaction, takes guard → period → entries in ID order → referenced evidence.
It checks the period is Draft, every entry is DRAFT/CALCULATED, and any current
v2 evidence has matching version, ownership and digest. V1/unknown versions and
inconsistent pointers fail rather than being migrated or erased silently.

It clears pointer, version, hash, calculation actor/time, all seven monetary and
eight count outputs, and resets entry status to DRAFT in ONE SQL UPDATE. It never
deletes or changes evidence rows or certifications. Compensation snapshots and
adjustments remain intact. Full current source/certification validity is NOT a
prerequisite to withdrawing a stale Draft calculation, preventing a revocation
dead end. The next calculation still requires all authoritative checks to pass.

APPROVED/PAID period or entry history is rejected. Failure rolls back when the
caller rolls back. This helper is not connected to active edit/adjustment routes;
the previously documented production pointer-invalidation integration remains
future work.

## Historical certification digest compatibility

The actual 006 application projection hashed format-1 certification content before
`correction_reason` and `correction_reference` existed. After 007 the same stored
rows acquire two NULL columns, so using only the new projection would reject their
unchanged stored seal.

New publication continues to use the exact existing projection and hash. During
v2 eligibility validation, AFTER all current authoritative-source checks, the
read-only verifier accepts:

- The existing current projection, or
- The exact known original 006 projection, excluding ONLY those two added fields,
  and ONLY if both extension fields are NULL.

Unknown evidence-format versions, altered content, non-NULL corrections with an
old-format seal and unmatched digests fail. There is no user-selectable projection,
fallback to an older certification revision, recalculation of salary, resealing,
backfill, trigger change or update to stored hashes/events. Unit tests independently
express the old projection. MySQL tests publish a real synthetic 006 certification,
apply 007 twice, verify old history is unchanged, then validate/persist evidence
through that historical seal. Existing 007 publication/audit tests verify the
current format remains unchanged. No 004–007 migration source changes are needed.

## Failure and concurrency verification

The multi-employee fixture uses one 30,000 PHP employee with approved synthetic
earnings 500/deduction 300 (net 15,200), and one 20,000 PHP employee with one
absence in an 11-workday cutoff (net 9,090.91).

Snapshots of periods, all entries/evidence, certifications/members/events and
central Audit Logs prove no partial commit on rejected operations. Tests cover:

- Policy, authority/certification and second employee eligibility/calculation
  failures; monetary overflow; real SQL evidence-INSERT, output-UPDATE and pointer
  failures; precommit failure; failed recalculation and invalidation.
- Output/pointer failures use separate predicates on the SAME atomic UPDATE, not
  an artificial split of the business operation.
- Cursor persistence remains invisible to another connection until caller commit;
  caller rollback removes it, including with explicit autocommit=1 transactions.
- First success stores one evidence row per included employee. A stale replay is
  rejected. Explicit recalculation appends sequences without deleting history.
- Two queued period calculations assert TWO actual InnoDB guard waits; exactly
  one whole-period calculation succeeds with the shared fixture.
- A real lock timeout (1205) and real InnoDB deadlock (1213) cause whole-period
  rollback. The deadlock occurs after the first employee wrote evidence, using a
  deliberately nonparticipating external test session with reversed lock order;
  application code remains guard-first. A disposable test table supplies victim
  weight, not a new application migration.
- A real compensation writer waits behind dirty calculation; reverse ordering
  makes calculation observe changed compensation and reject. Changed roster
  population also fails; no mixed source revision is committed.
- Real certification revocation waits behind dirty preparation, then blocks later
  calculation. Stale/revoked Draft evidence can still be invalidated safely.
- Protected period/entry status and unknown/v1 invalidation tests reject changes.
  Existing historical APPROVED/PAID, freshness, authorization, CSRF and audit suites
  remain regression checks, not newly changed business rules.

## Commit uncertainty, security and remaining limits

A failure injected BEFORE commit leaves no changes. A lost acknowledgement AFTER
the server commits cannot be undone by rollback: the test observes a complete
two-entry commit and rejects replay using the old markers. This is not durable
request idempotency or a general solution for uncertain distributed commits.
Inspect committed state before retrying; no UUID or new schema mechanism is added.

No synthetic central success audit event is emitted. Production routes retain
their existing permission, fresh-request authorization, CSRF, state and best-effort
postcommit audit behavior. Certification's required events remain transactional.
Request-start authorization does not necessarily cancel a request revoked while
waiting; this checkpoint changes none of those semantics.

The global guard serializes participating writers, not old workers, direct SQL
or external HR systems. Content restored to exactly its old value can match again;
explicit revocation remains permanent. No production-scale performance claim is
made. Real adapters, authoritative sources, formula/odd-cent/deduction approvals,
separation of duties, legacy-v1 cutover and coordinated deployment remain pending.

## Run

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -q
.venv/Scripts/python.exe tests/mysql_payroll_period_atomicity_smoke.py
node --test tests/horizontal_navigation.test.cjs
```

The MySQL script creates a fresh synthetic server/database; it does not apply
migrations to actual databases. No browser-facing behavior changed, so no Chrome
workflow is introduced for this checkpoint.

## Final verification

Starting branch/HEAD confirmed as `fix/payroll-reliability` / `8b5d4e3`.
The interrupted verification was resumed without replacing the implementation.
The completed 27-suite disposable MySQL regression result is retained; resumed
verification reran all 359 Python tests, all 11 JavaScript tests, and both the
period-atomicity and existing evidence MySQL suites, all passing. Those targeted
reruns include actual InnoDB waits, 1205/1213 rollback, later-employee failures,
historical 006 seals upgraded through 007, and public persistence compatibility.

Compilation passed for 126 Python files and 114 Jinja templates with database
access blocked during compilation. Dependency, JavaScript syntax, diff/new-file
whitespace and changed-file credential checks passed. Only explicit synthetic
credentials occur in the new test fixtures. No accidental/unrelated files or
production adapter callers were found. Protected routes, formulas, v1/v2 wire
formats, migrations, permission definitions, security and payment logic remain
unchanged. The extracted persistence statements match the original business
statements apart from SQL indentation; public transaction ownership is covered
by unit and disposable MySQL tests.

Ready for review as a development-only Git checkpoint, not production calculator
activation. No commit, push or next-checkpoint implementation was performed.
