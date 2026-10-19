# HR Step 3.2B: internal read-only foundation

Starting checkpoint: `b988a68` on `fix/hr-employee-reliability`. This checkpoint
adds no migrations, application routes, navigation, permissions, production fixture
adapters, current-state synchronization, publication, or approval writes. Payroll
is untouched. Migration 008/009 definitions and protections remain unchanged.

## Repository API

`hr_lifecycle_repository.py` exposes these internal functions:

| Function | Result |
| --- | --- |
| `get_lifecycle_status(employee_id)` | Employee ID, managed flag, current revision |
| `list_employment_periods(employee_id, limit=50, offset=0)` | Raw period projections, including void/open/closed rows |
| `list_employment_events(employee_id, limit=50, offset=0)` | All historical events, including corrected rows and immediate successor ID |
| `get_employment_event(employee_id, event_id)` | One Employee-scoped event and successor link |
| `list_lifecycle_requests(employee_id, limit=50, offset=0)` | Proposals with original submission and decision metadata |
| `get_lifecycle_request(employee_id, request_id)` | One Employee-scoped immutable proposal and decision |
| `get_correction_relationships(employee_id, event_id)` | Immediate predecessor/successor IDs; no history rewriting |
| `get_history_coverage(employee_id, start, end_exclusive)` | Bounded-window period coverage, unknown intervals, raw nonvoid overlapping periods, legacy-observation count, managed flag/revision |

Every list uses parameterized SQL with page size 1–100 and offset 0–100,000.
IDs are typed positive signed INT (Employee) or BIGINT (history identities); bool,
float, numeric strings, negative and oversized values are rejected before DB access.
Invalid inputs raise `LifecycleInputError`; missing or differently scoped details
return `None`, and empty lists return `[]`. No Employee names, contact details or
current hire/status fields are fetched to infer missing history. JSON columns are
returned in the connector's native representation (currently JSON text), preserving
stored proposals rather than silently reinterpreting older content.

Events order by effective DATE, explicit order, publication revision, then event ID.
Requests order by proposed DATE/order/request identity; they have no publication
revision. Periods order by start DATE/sequence/identity. Recorded timestamps never
define effective chronology. Deterministic ordering resolves technical ties without
approving same-day business precedence. Each page uses a fresh snapshot: separate
pages are not a frozen export if concurrent inserts change earlier offsets. A future
snapshot-export or keyset-pagination contract needs its own reviewed checkpoint.

## Coverage semantics

Only nonvoid recorded verified-period projections contribute to coverage. Their
intervals are clipped to the requested `[start, end_exclusive)` DATE window and
unioned, including overlapping projections. This does not validate overlaps or
independently authenticate sources. The response explicitly reports
`source_verification_performed=False` and calls its result
`recorded_period_coverage`, not certified employment eligibility.

All uncovered intervals mean **unknown historical coverage**, never proof of
nonemployment. A missing period, managed flag, current hire date/status or observed
legacy fact cannot fill a gap. An unmanaged Employee can have recorded periods;
readers return both facts without marking that Employee managed or verified.
`observed_legacy_event_count` counts raw LEGACY_OBSERVATION events within the
window, including any superseded observations. It is not a verified-fact count;
inspect event successor links for correction context. No automatic correction or
void application to period projections is implemented.

Coverage returns `None` for a missing Employee. It reads at most 1,001 overlapping
nonvoid periods and refuses more than 1,000 rather than presenting truncated data
as complete coverage. Narrow the window if needed. Sorting/count queries can still
scan many historical rows: no production-scale performance guarantee is claimed.

## Synthetic structural validation

`hr_lifecycle_validation.py` is pure and performs no database lookup. It validates
a **synthetic v1 envelope**, not an approved live publication API:

* Required schema version, typed Employee/actor/revision/order references, supported
  event label, effective DATE, source type/reference, reason and changes object.
* Nullable optional period/correction IDs; CORRECT/VOID require a correction ID,
  while other labels cannot carry one. Reference existence, same-Employee ownership
  and earlier publication revision remain database/repository concerns.
* Actual MySQL DATE range without implicit parsing or timestamps; positive bounded
  IDs/revisions; source/reason bounds matching 009 (30/255/50/255 characters).
* Explicit changes: omitted field means unchanged; `{"op":"clear"}` means an
  intentional clear; `{"op":"set","value":...}` requires a non-null typed value.
  Current structural field vocabulary is department ID, job title, employment
  status, verified start DATE and end-exclusive DATE. Unknown fields/operations
  are rejected. Date change values are encoded as ISO dates in the detached result.
* JSON-object helper rejects unsupported types, nonfinite numbers, non-string keys,
  oversized integers, invalid Unicode, cycles/excess nesting and serialized UTF-8
  payloads over 16,384 bytes. The result is detached from caller-owned data.

No label-specific required changes, status eligibility, source authenticity,
field-clear eligibility, separation mapping, period overlap, same-day precedence,
or approval separation is inferred. Structurally valid data may be impossible or
unauthorized to publish. Even a syntactically valid clear operation on a required
business field is not permission to persist NULL. Future publication must add
reviewed semantic validation and coordinated transaction protections. The synthetic
envelope is not installed as a new database JSON constraint or migration.

## Transactions and confidentiality

Each call obtains a dedicated existing-convention database connection, starts an
explicit READ ONLY / REPEATABLE READ consistent snapshot, executes SELECTs, and
ends with rollback/close. Coverage's multiple queries share one snapshot. There
are no row locks, commits, mutations or revision changes. There are no import-time
connections; the existing database module retains its usual environment loading.

Storage/configuration failures expose only `LifecycleReadError` with a fixed
message, without SQL, sources, form content or infrastructure details. This is
internal error isolation, not an authorization system. Results include sensitive
source/reason/proposal data. Future callers must authorize each Employee and field
set using fresh authorization before exposing these functions. No new public route
or role grant exists. A SELECT-only database role is recommended as an additional
boundary; production credentials/grants have not been changed.

## Verification and remaining decisions

Unit tests cover structural boundaries, unchanged/clear distinctions, parameterized
SELECT-only calls, transaction cleanup, scoped input and confidential errors.
`mysql_hr_lifecycle_read_smoke.py` uses only a fresh verified disposable MySQL datadir,
synthetic direct-SQL fixtures and a SELECT-only reader account. Strict/non-strict
tests cover no history, multiple/void/open/closed/overlapping periods, backdated
corrections, deterministic pagination, cross-Employee isolation, legacy observations,
concurrent reads, concurrent fixture insertion during coverage, coverage refusal,
and unchanged records/revisions. Existing 009 invariant tests run separately without
altering the approved migration or triggering production publication routes.

No schema-contract defect was found during the invariant regression. Browser tests
are unnecessary because no browser behavior changes. Future transition policies,
source verification, independent approvals, separation-date mapping, same-day and
backdated rules remain pending. No production publication should begin from this
checkpoint without a separately approved implementation.
