# Development-only monthly calculator prototype (5B.4)

This is hypothetical calculation research using synthetic fixtures. It is not a
company-approved salary policy, production calculator, statutory compliance
implementation or payroll-processing endpoint. Do not supply real employee data.

Only three files are added: `payroll_monthly_prototype.py`,
`tests/test_payroll_monthly_prototype.py` and this document. No existing production
file, database schema/migration, role grant, route, template, evidence record or
APPROVED/PAID history is changed. No new runner reads configured databases.

## Pure, explicit interface

`calculate(CalculationInput(...))` returns a frozen `CalculationResult`. Inputs are
frozen dataclasses containing only explicitly supplied policy, cutoff, synthetic
eligibility, Decimal monthly salary, attendance, approved daily leave and approved
adjustments. Collections must be tuples; dates must be actual `date` objects,
not strings or datetimes. Amounts must be `Decimal`, not floats, strings, booleans
or integers. Synthetic supporting references start with `SYNTHETIC:`. These labels
do not authenticate evidence or prove that a caller supplied truthful data.

All data must be provided by the development caller. There are no database,
Flask, application, repository, evidence-service or clock imports/calls. The sole
ERP import is the existing pure `payroll_validation.payroll_money` validator.
Importing the module performs no calculation or application work. The tests
provide explicit synthetic fixtures; there is no default policy argument, current
date lookup, implicit employee selection or configuration execution.

The caller must construct `HypotheticalPolicy` explicitly. Every field is
allowlisted to exactly the following scenario; unknown constructor keywords fail
and other values/shapes raise validation/unsupported-policy errors. The synthetic
engine key `HYPOTHETICAL_MONTHLY_PROTOTYPE_V1` deliberately differs from the
production policy/evidence engine key.

## Hypothetical policy and eligibility contract

- `development_only=True`, scenario `HYPOTHETICAL_MONTHLY_V1`, SEMI_MONTHLY,
  MONTHLY compensation, PHP, divisor 2 and Monday–Friday mask 31.
- Calendar `SEMI_MONTHLY_1_15_16_EOM_V1`: A is 1–15 inclusive; B is 16–month end
  inclusive. Exact whole cutoffs only, including Gregorian leap-year rules.
- Decimal ROUND_HALF_UP at two monetary decimal places.
- PRESENT/LATE/approved paid leave consume zero deductible day units;
  ABSENT/approved unpaid leave consume one; HALF_DAY consumes 0.5.
- Missing evidence, proration, calendar exceptions, odd-cent reconciliation and
  excess deductions are BLOCK. No holidays, premiums, overtime, statutory rates,
  tax, employer contributions or alternative executable formulas are supported.

`SyntheticEligibility` must explicitly assert FULL_CUTOFF eligibility and the exact
requested cutoff, known hire date no later than cutoff start, employment and
compensation coverage spanning the entire cutoff, synthetic supporting references,
MONTHLY/PHP compensation, exactly all derived weekday dates, and no calendar
exceptions. No Active-status inference exists. Missing/partial coverage, DAILY,
HOURLY, alternative currency/schedules, holidays or special-pay cases fail.

Each scheduled day requires one attendance record. Extra unscheduled/weekend or
out-of-cutoff attendance is rejected rather than silently ignored. ON_LEAVE
requires exactly one approved daily leave classification and vice versa. Duplicate
attendance, duplicate/conflicting leave, missing evidence, unapproved leave and
non-boolean paid classification fail. The input is explicitly daily leave, not an
inference from a leave request's aggregate duration. Future source adapters would
need to establish that mapping authoritatively.

Adjustments are positive exact amounts, EARNING or DEDUCTION, explicitly approved,
and identified by unique synthetic fixture references. Duplicate identifiers fail
instead of double counting. Attendance, eligibility schedule and adjustment input
order does not affect results or itemization order.

## Mathematics, monetary limits and rounding

1. Validate salary as a positive DECIMAL(12,2) amount (maximum 9,999,999,999.99).
2. Calculate exact base `salary / 2`. If the base cannot be represented in whole
   cents, reject the salary before returning a result. Thus 30,000.01 is rejected;
   it is never independently rounded to 15,000.01 twice. Supported bases are
   returned with two decimal places.
3. Derive `N`, the scheduled weekdays in the exact cutoff. Return the daily
   calculation rate `base / N` at 50 significant Decimal digits and the exact
   rational pair `(base, N)`. A recurring quotient cannot be represented exactly
   by a finite Decimal; its rational pair retains the exact mathematical value.
   The displayed daily rate is separately rounded to two places.
4. Aggregate deductible units `U` from all daily classifications FIRST. Attendance
   deduction is `ROUND_HALF_UP((base * U) / N, 2)`, rounded once. It is not
   calculated from the displayed daily rate, nor by rounding deductions per day.
   Multiplication before division also preserves exact half-cent cases that can
   be obscured by multiplying an already approximated repeating quotient.
5. `earnings = sum(approved EARNING amounts)`;
   `other_deductions = sum(approved DEDUCTION amounts)`.
6. `gross = base + earnings`;
   `total_deductions = attendance_deduction + other_deductions`;
   `net = gross - total_deductions`.
7. Validate aggregate earnings, aggregate deductions, all seven storage-shaped
   monetary outputs and net against DECIMAL(12,2). Reject overflow, excess input
   precision, nonfinite values and negatives. If deductions exceed gross, reject
   instead of clipping net to zero. Exactly zero net is allowed.

The calculator owns a local 50-digit Decimal context with explicit rounding,
exponent limits, flags and traps, leaving the caller's context unchanged. Validated
monetary inputs have at most 12 significant digits and each cutoff at most 12
weekdays; the aggregated numerator stays small enough to resolve cent boundaries
reliably. Independent integer/Fraction tests verify all possible half-day unit
totals for five salaries across all 24 cutoffs of leap year 2028 (2,720 cases).

The auxiliary high-precision daily rate and day equivalents are calculation
details, not DECIMAL(12,2) storage cells. Only the displayed `daily_rate` belongs
in the current evidence's two-place output vocabulary.

Results include scheduled dates, every resolved daily classification and its
deductible units, ordered adjustments, all counts, exact rate numerator/denominator,
money totals and an immutable itemized `CalculationStep` explanation.

## Independently checked synthetic examples A–G

Shared exact inputs: cutoff A, 2035-01-01 through 2035-01-15; salary
`Decimal('30000.00')`; N=11, covering January 1–5, 8–12 and 15; synthetic full
employment/rate coverage for those inclusive dates; no calendar exceptions.
Every scheduled day is PRESENT unless changed below. Each leave example supplies
ON_LEAVE attendance plus an explicitly approved daily leave fixture. All other
earnings/deductions are zero.

For every row, base is 30,000/2 = **15,000.00**; exact daily rate is 15,000/11;
50-digit rate is `1363.6363636363636363636363636363636363636363636364`;
display rate is **1,363.64**. `U` is the aggregate deductible day equivalent.

| Case | Exact changed inputs | U | Deduction calculation → rounded | Gross | Total deductions | Net |
|---|---|---:|---|---:|---:|---:|
| A | All 11 PRESENT | 0 | 15,000 × 0 / 11 → 0.00 | 15,000.00 | 0.00 | 15,000.00 |
| B | Jan 1 ABSENT; 10 PRESENT | 1 | 15,000 / 11 → 1,363.64 | 15,000.00 | 1,363.64 | 13,636.36 |
| C | Jan 1 HALF_DAY; 10 PRESENT | 0.5 | 7,500 / 11 → 681.82 | 15,000.00 | 681.82 | 14,318.18 |
| D | Jan 1 ON_LEAVE, approved paid; 10 PRESENT | 0 | 0 / 11 → 0.00 | 15,000.00 | 0.00 | 15,000.00 |
| E | Jan 1 ON_LEAVE, approved unpaid; 10 PRESENT | 1 | 15,000 / 11 → 1,363.64 | 15,000.00 | 1,363.64 | 13,636.36 |
| F | Jan 1 LATE; 10 PRESENT | 0 | 0 / 11 → 0.00 | 15,000.00 | 0.00 | 15,000.00 |
| G | All PRESENT, approved earning 500.00 and deduction 300.00 | 0 | 0 / 11 → 0.00 | 15,500.00 | 300.00 | 15,200.00 |

For G, earnings are 500.00, other deductions 300.00; gross is 15,000+500 and
net is 15,500−300. The tests assert every expected amount above independently.

## Rejections H–N and precision/overflow examples O

All scenarios below otherwise reuse A's explicitly synthetic eligibility and
evidence, with coherent changes where applicable. They return no plausible salary.

| Case | Exact input/change | Expected result |
|---|---|---|
| H | Salary 30,000.01 | Reject odd-cent reconciliation: base 15,000.005 requires an unapproved decision. |
| I | Approved deduction 15,000.01 with A's gross 15,000.00 | Reject excess deductions; never floor −0.01 to zero. A deduction of exactly 15,000.00 gives valid net 0.00. |
| J | Hire date 2035-01-02 for A | Reject mid-cutoff hire/proration. |
| K | Eligibility pay_type DAILY | Reject unsupported pay type. |
| L | Eligibility pay_type HOURLY | Reject unsupported pay type. |
| M | Omit Jan 15 attendance; or PRESENT Jan 1 plus approved leave Jan 1; or ON_LEAVE without leave; or two approved leave classifications for Jan 1 | Reject missing/contradictory/duplicate evidence. |
| N | A labeled 2035-01-01–2035-01-05 (five weekdays) | Reject arbitrary period despite complete weekday attendance. |
| O1 | Salary 0.02; N=11; five ABSENT (U=5) | Base 0.01; deduction 0.05/11 → 0.00; net 0.01 (below half-cent). |
| O2 | Salary 0.02; five ABSENT plus one HALF_DAY (U=5.5) | Deduction 0.055/11 = 0.005 → 0.01; net 0.00 (exact half-cent). |
| O3 | Salary 0.02; six ABSENT (U=6) | Deduction 0.06/11 → 0.01; net 0.00 (above half-cent). |
| O4 | Salary 0.06; five ABSENT plus one HALF_DAY | Base 0.03; deduction 0.165/11 = 0.015 → 0.02; net 0.01, even though display daily rate is 0.00. |
| O5 | Salary 9,999,999,999.98 and approved earning 5,000,000,000.00 | Base 4,999,999,999.99; gross/net exactly 9,999,999,999.99 accepted. |
| O6 | O5 earning increased by 0.01 | Gross 10,000,000,000.00 rejected before any result. |
| O7 | Earnings or deductions 9,999,999,999.99 plus 0.01 in two individually valid adjustments | Aggregate overflow rejected. |
| O8 | Salary 30,000.000; NaN; Infinity; negative/zero salary; malformed amount types | Reject excess precision, nonfinite, invalid compensation or non-Decimal input. |

Additional rounding regression: three ABSENT days under A deduct
45,000/11 → **4,090.91**, not `1,363.64 × 3 = 4,090.92`.
Two ABSENT plus one HALF_DAY deduct 37,500/11 → **3,409.09**; net **11,590.91**.

For cutoff B, February 16–29, 2028 has ten scheduled weekdays, so salary
30,000.00 yields base 15,000.00 and daily rate 1,500.00. Nonleap 2027/2100,
leap-century 2000 and upper-bound December 9999 are tested separately.

## Version-2 evidence compatibility and future integration

`result.as_evidence_outputs()` returns a fresh in-memory mapping with exactly the
existing seven money and eight count output names. It writes nothing, has no
policy/certification/employee identities, and generates no version-1/version-2
fingerprint, evidence row or current pointer. Explanation-only rate precision,
deductible equivalents, source fixtures and `other_deductions` remain outside that
15-field mapping.

An approved future implementation would first authenticate the existing route's
actor and preserve CSRF, then acquire the shared coordination guard and validate
policy pinning, latest authoritative certification, complete roster, compensation,
calendar and source freshness in the existing transaction. An independently
approved engine would consume that validated context. Only then could its outputs
be passed to evidence construction/persistence in the SAME transaction as entry
updates, with postcommit best-effort audit logging. Existing submission, approval
and payment repositories would retain authorization and transition checks.

None of those integrations is implemented here. Do not call
`payroll_evidence_repository.persist_proposed()` with this prototype's results.
Its hypothetical policy shape and engine key are not production-approved. The
production policy vocabulary also does not currently encode this prototype's
odd-cent rejection as a distinct explicit choice; any future vocabulary/schema
change needs separate review. No migration is proposed or created at this stage.

## Isolation and remaining decisions

Production routes/repositories do not import or invoke this module. The isolation
test checks production imports and uses a fresh interpreter that rejects DB,
Flask, application and repository imports, filesystem writes, network access and
subprocess creation while importing/calculating explicit synthetic data. It also
checks for implicit clock calls and dynamic formula execution. No configured
database or real salary record is read by the prototype. Existing disposable
integration suites separately verify unchanged workflows with synthetic data.

Existing production limitations remain: the old monthly calculator still uses its
fixed half-month formula, DAILY/HOURLY production calculation is incomplete,
entry compensation remains a generated snapshot, and production workflows remain
v1-only. The v2 foundation's authoritative HR/calendar adapter is still unavailable.
Its pending cutover, legacy verification/correction process and invalidation-pointer
integration remain separate work. This prototype fixes none of those production
limitations and must not be used to bypass them.

Before any production calculator, company approval is still required for salary
frequency/formulas, eligibility/proration, weekday/holiday schedules, late/absence
and leave treatment, overtime/special pay, statutory and manual deductions,
excess-deduction handling, payment attribution/reconciliation, approval separation,
authoritative source adapters and evidence/version transition rules.

Odd-cent alternatives for future discussion ONLY: explicitly balance the second
cutoff to the approved monthly total; or use an approved higher-precision accrual
and reconciliation process. Independent rounding of both halves can overpay one
cent and is not implemented. No balancing, accrual, carry-forward or reconciliation
rule has been selected by this prototype.

## Run synthetic tests

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_payroll_monthly_prototype.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -q
node --test tests/horizontal_navigation.test.cjs
```

No Chrome workflow is added: routes, templates and JavaScript are unchanged.
The calculator has no browser or command-line production endpoint.

Checkpoint results: 354 Python tests passed, including 26 new prototype tests and
the 2,720 independent rounding-oracle cases within them; 11 JavaScript tests passed;
all 26 existing disposable MySQL smoke suites passed (Payroll, Finance,
Procurement/receiving, Inventory, IT Assets/Help Desk authorization, central audit
and security). Python compilation/syntax passed for 123 files and Jinja compilation
for 114 templates with database access blocked during compilation. `pip check`,
JavaScript syntax, tracked diff checks and new-file whitespace checks passed.
Existing tracked files are byte-for-byte unchanged from starting HEAD `81dd6bf`.
No production-readiness or company-policy approval is implied by these results.
