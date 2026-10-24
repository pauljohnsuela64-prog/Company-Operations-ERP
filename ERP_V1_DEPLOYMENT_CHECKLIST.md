# ERP v1 deployment prerequisites - no deployment authorization

This is a review checklist, not an instruction to operate on company systems.
Current approval covers local disposable synthetic verification only. No release
tag, public host, production migration or real Payroll operation is authorized.

## Decision and environment gates

- [ ] Owner approves target audience: synthetic demo, restricted pilot or production.
- [ ] Accept supported salary/pay-type/cutoff/lifecycle rules; resolve APPROVED recovery
  and PAID corrections before real Payroll use.
- [ ] Decide Purchase Request self-approval and historical UOM policy without rewriting history.
- [ ] Approve migration 010 rollout, worker coordination and inventory of external writers.
- [ ] Establish named operator, business owner, incident contact, training and rollback authority.
- [ ] Verify reviewed source SHA, required CI, dependencies and separate browser/test evidence.
- [ ] Provision a separate target with least-privilege application credentials; never use
  the disposable tests' synthetic root/no-password profile for a pilot or production.
- [ ] Verify MySQL 8.0.16+ with enforced CHECKs, InnoDB, selected database, required
  constraints, revisions, indexes, permissions and migrations. Do not grant new
  business permissions automatically to make readiness pass.

## Mandatory coordinated upgrade sequence

1. Obtain separate target-specific authorization. Verify selected host/port/database,
   backup scope, ownership and that no unexpected external writers exist.
2. Back up schema and business data consistently, retain required logs, protect backup
   credentials and verify restore on a separate approved target. Establish accepted
   RPO/RTO and restore decision criteria. The release test restored 32 synthetic
   tables; it did not rehearse any company backup or production recovery objective.
3. Drain/stop every Attendance, Leave and Payroll writer, worker, job and direct SQL
   integration. Keep them stopped through migration and coordinated deployment.
4. Inspect schema compatibility using the explicit operator tooling. Migration 010
   is additive and requires explicit host, port, user, database and password prompt;
   no application startup executes it. Never run it through workstation defaults.
5. Apply the separately approved migration and verify every integrity structure,
   nullable evidence column, guard row, CHECK, FK and engine. Do not backfill unknown
   evidence, reset generations or change historical statuses/amounts.
6. Treat MySQL DDL as implicitly committed. If interrupted, keep writers stopped,
   inspect the partial schema and explicitly resume/repair compatible additions.
   Do not assume a failed migration rolled all DDL back.
7. Deploy the approved new version to all participating workers together, with one
   stable secret and synchronized clocks. Missing structures can make the whole
   database-backed application unavailable, including login. Mixed writers are unsafe.
8. Verify /health/live and /health/ready, schema admission and access controls before
   any approved resumption. Never bypass readiness or freshness to resume service.
9. Reconcile legacy runs. DRAFT requires explicit calculation; PROCESSING requires
   authorized return-to-Draft then calculation/resubmission. Stale/unknown APPROVED
   payment stays blocked until separately approved recovery exists. PAID remains intact.
10. Resume approved writes gradually, monitor errors/latency/guard waits/connections,
    reconcile uncertain transactions and verify audit/domain histories. No automatic
    replay after an uncertain commit; receiving reconciliation retains the same UUID.

## Runtime security and hosting

- [ ] Explicit ERP_ENV=production, ERP_DEBUG=false; reject missing/example/short keys.
- [ ] Supply a high-entropy SECRET_KEY outside Git, stable across workers; control rotation.
- [ ] Supply DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME through managed configuration.
- [ ] Use a supported WSGI server, never Flask's development server/debugger publicly.
- [ ] Verify actual TLS termination, Secure/HttpOnly/SameSite=Lax cookies and session
  expiry through the real proxy. Local HTTP tests verify a different profile.
- [ ] Explicitly validate public hosts, trusted proxy hop counts, redirects, HSTS/CSP,
  secret/error logging, login abuse controls, network access and export authorization.
- [ ] Select trusted static asset/CDN/offline strategy. Bootstrap is pinned to 5.3.8;
  a pinned URL alone is not a complete asset integrity policy.
- [ ] Set monitoring/alerts for readiness, DB connections, locks, disk, backup failures,
  audit failures and uncertain operations; verify log retention and access controls.
- [ ] Conduct company-user UAT, realistic bounded load, physical-device and accessibility
  checks where required. Document supported browsers and print behavior precisely.

## Rollback and incident limitations

Retain additive 010 structures while new workers can run. Reverting application
code to old writers forfeits freshness guarantees; do not resume them as an
integrity-preserving rollback. Backup restoration must reconcile later business
writes and external payment state. Never silently replay payments, overwrite PAID
history, fabricate evidence or implement recovery through ad hoc SQL. An audit row
can be missing after a committed business write; reconcile persisted state first.

No item above is checked merely because automated tests passed. Target-specific
operator evidence and owner sign-offs remain required.
