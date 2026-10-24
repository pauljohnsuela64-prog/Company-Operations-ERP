# Company Operations ERP v1 development milestones

This describes implemented development milestones, not a published release or
production certification. No v1 tag or GitHub release was created.

## Foundation and integrated operations

- Flask/MySQL modules for user/role administration, HR, Attendance/Leave, Inventory,
  Warehouses, Procurement, Finance, Payroll, IT Assets and Help Desk.
- Permission-aware navigation, refreshed authorization, signed-session credential
  binding/expiry and CSRF-protected writes with recoverable validation feedback.
- Decimal stock/financial handling, transaction locks, UUID receiving/manual-stock
  duplicate protection, domain histories, best-effort central audit and reports/exports.
- Explicit migrations, global schema compatibility admission and disposable synthetic
  regression infrastructure. Business-policy limitations remain documented.

## Assignment 1 - GUI completion

Merged GUI completion ancestry includes 1f8d47c4dcd4a5549dfd748a5c7aa33bf44eea5c
and PR #29 merge ee7e49b061a43891d9593f251fcf868004e85e2d. Professional navy/slate
workspace headers, tables/forms, responsive navigation, filters, pagination, empty/
unavailable states, long-text handling and keyboard/label improvements cover the
implemented modules. Static visual modernization did not certify business policies.

## Assignment 2 - cleanup and Payroll integrity

PR #30 merged at 4b927555c5e76aa236bf9924895daec4c27198df, with nine reviewed
feature commits and 48 cumulative changed files. Fixed unsafe receiving replay
after uncertain outcomes, Payroll overlap races, Supplier native email mismatch
and authentication resource cleanup. Added migration 010 and durable Attendance
generations/calculation evidence coordinated through a transaction guard.

Stale/unknown evidence now blocks submission, approval and payment. Legacy evidence
is not fabricated, APPROVED is not automatically reopened and PAID is not rewritten.
Existing salary arithmetic is unchanged. Migration rollout and recovery need approval.

## Assignment 3 - release verification (local work)

Independent merged-baseline test runs, module/permission inventory, dedicated
synthetic migration/access and backup/restore rehearsal, bounded guard timing,
five-width GUI review and additional automated AX/keyboard/Edge checks.

Corrected only stale test expectations for already approved Payroll retained values
and Supplier text input. Added release evidence and readiness/known-issue/deployment
documents. No new runtime feature, business policy, production migration, deployment,
push, merge or release tag is part of Assignment 3. Final executed results and
remaining gaps belong to ERP_V1_TEST_REPORT.md and ERP_V1_RELEASE_READINESS.md.
