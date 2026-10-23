# ERP v1 release readiness

Verified release baseline: **4b927555c5e76aa236bf9924895daec4c27198df**.
PR #30 is merged; Assignment 1 GUI and all nine Assignment 2 commits are ancestors.
Mainline ERP CI [run 39917785782](https://github.com/pauljohnsuela64-prog/Company-Operations-ERP/actions/runs/39917785782)
completed successfully in all three jobs. This document assesses implemented scope,
not hypothetical features or unapproved company operating policies.

## Executive assessment

All required local verification groups completed, including affected browser
retests. Essential integrated synthetic workflows pass. Production operating
policies and safeguards remain unapproved or unverified. No runtime feature,
business policy, company migration, public deployment or paid history was changed.

| Release category | Assessment at this checkpoint | Boundary |
| --- | --- | --- |
| Portfolio/Demo v1.0 | READY for isolated synthetic demonstration | Isolated local synthetic data only; supported monthly Payroll demonstration, explicit limitations and no real payment/company use |
| Controlled Internal Pilot | NOT READY | Owner policies, pilot scope/environment, real permissions, recovery, operations, training, monitoring and target-specific migration approval remain missing |
| Production Deployment | NOT READY | Essential operating safeguards, salary/lifecycle/recovery decisions, target migration/rollback, TLS/proxy, capacity and user acceptance are not certified |

## Evidence-backed engineering assessment

- Fresh merged-baseline Python/navigation/syntax/dependency checks passed. All 38
  disposable SQL smoke suites now passed across the initial completed prefix and
  resumed remainder; a sandbox bind failure was not treated as a suite pass.
- Integrated Procurement receiving affects exact stock balances with UUID deduplication;
  uncertain commit/rollback cases and concurrent stock/payment/schedule operations
  retain existing transaction and audit boundaries.
- Payroll freshness explicitly covers old/new employee/date keys, same-second/ABA
  changes, insertions, effective Leave changes, cutoff changes, complete snapshots,
  stale submit/approve/pay, legacy unknown evidence and both source/Payroll orderings.
  Sixteen races pass under RR and RC; actual timeout/deadlock and lost-acknowledgment
  tests pass without unsafe replay. Salary arithmetic remains unchanged.
- Legacy DRAFT/PROCESSING needs authorized explicit recalculation; unknown/stale
  APPROVED payment remains blocked without automatic reopening. No evidence bypass
  or PAID rewrite was added. APPROVED/PAID recovery remains an unimplemented proposal.
- New synthetic rehearsal proves fresh/pre-010/post-010 application admission,
  partial/repeated upgrade preservation and exact dump/restore of 32 tables. Restored
  stale evidence rejects, explicit recalculation then submit/approve/pay succeeds,
  and old PAID entry values remain unchanged.
- Chrome full GUI checks pass at 1440/1024/768/390/320, including role-aware actions,
  forms/tables/states/validation/print styling and JS exceptions. Additional automated
  AX/Tab checks pass on 55 page-width cases. Human accessibility remains untested.
- Security checks cover actual login, expiry/invalidation, permission changes,
  denied/read-only requests, CSRF, escaping, injection-shaped filter inputs, exports,
  schema outage/recovery and last-admin protections. They do not certify a public host.

The complete workflow/permission/source/procedure/result matrix is in
ERP_V1_RELEASE_VERIFICATION_PROGRESS.md; tests and limitations are in
ERP_V1_TEST_REPORT.md and ERP_V1_KNOWN_ISSUES.md. Passing a described procedure
does not imply every possible workflow combination or business policy is certified.

## Owner decision register

| Decision | Synthetic portfolio/demo | Controlled internal pilot | Production |
| --- | --- | --- | --- |
| PR creator self-approval/rejection | Demonstrate existing behavior and disclose it | Owner accepts or approves separation of duties and exceptions | Formal acceptance/enforcement and actor-aware audit design as required |
| Historical UOM/master labels | Explain live-label behavior; no conversions | Owner accepts supported editing/history rules | Approved freeze/version/conversion and historical display semantics |
| Salary/cutoff/pay-type/lifecycle | Clearly label supported MONTHLY/weekday synthetic calculation; no salary certification | Explicit supported population/cutoffs/rounding/proration/leave acceptance; prohibit unsupported use | Formal Payroll/HR/Finance approval, employment lifecycle integration and salary acceptance |
| Unknown/stale APPROVED recovery | Show payment rejection; do not bypass | Approve reconciliation and correction/reopening/replacement before affected real runs | Tested authorized recovery with separation of duties and audit evidence |
| Already-PAID corrections | Do not modify demonstration history | Approved correction/reversal process before real payment use | Formal accounting/payment reconciliation and reversal policy; no history overwrite |
| Migration 010 rollout | Fresh disposable schema/rehearsal is sufficient for synthetic demo | Target-specific approval, backups, drain, coordinated workers and readiness | Audited migration/rollback/restore plan and operator sign-off |
| External writers and worker compatibility | Only cooperating test writers | Inventory and control all pilot integrations | Proven coordination for every worker/job/direct SQL integration; prohibit mixed writers |
| Operational safeguards | Bind isolated loopback, synthetic secrets/data | Authorized pilot host, least privilege, restore, monitoring, support and training | Verified WSGI/TLS/proxy/hosts, abuse controls, backup/RPO/RTO, capacity, incident response and UAT |

## Performance and operational limits

Observed local guard timing is small and bounded: one employee/five weekdays,
twenty serial calculations plus twelve across four workers. Other checks ran
concurrently. It establishes neither an SLA nor production capacity. High-volume
parallel browser testing hit Windows socket exhaustion; repeat affected checks
with reduced concurrency and qualify connection churn/host limits in staging.
Do not weaken the global integrity guard to improve benchmark numbers.

No company database, public TLS/proxy, actual backup objectives, production privileges,
live monitoring, physical devices or human screen readers were verified. Tests use
root/no-password only inside owned disposable servers. Production credentials
and least privilege must be reviewed independently.

## Recommendation

A clearly labeled isolated synthetic demo may proceed within the documented
supported scope. Do not begin an internal pilot or production rollout until
the applicable decision/operations gates above are explicitly approved and verified.
Use ERP_V1_DEPLOYMENT_CHECKLIST.md for the required backup/drain/migrate/coordinated
deploy/readiness/resume sequence. This checklist does not authorize execution.

All Assignment 3 work remains local for human review. No push, merge, release tag,
GitHub release, production migration or public deployment is authorized.
