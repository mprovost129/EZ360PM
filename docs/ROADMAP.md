# EZ360PM Roadmap (Locked After Phase 3A Layer 2)


## Current Hardening Track (Phase 3F → 3J)

### Completed
- **3F** Financial integrity + credit notes + reconciliation (baseline)
- **3G** Backup & Recovery (DB dump + optional media + retention + soft-delete guardrails)
- **3H** Monitoring & Observability (healthz, request-id, slow request logging, optional Sentry)
- **3I** UX polish (onboarding checklist, dismissible alerts, cleanup)
- **3J** Client Credit Ledger + Auto-Apply Credit
- **3K** Ops Console + Support Mode (staff-only)
- **3L** Ops Timeline + Stripe Subscription Diagnostics (staff-only)
- **3P** Launch Readiness Checks (staff-only UI + ez360_check command)
- **3Q** Ops Retention & Pruning (staff-only UI + ez360_prune command)
- **3R** Security Defaults (production-on email verification gate, secure cookies/HSTS/SSL defaults, default company 2FA policy)

### Next (Planned)
- Stripe refund linkage
- Operational alerts (email/Slack) + SLO dashboards
- PII export tooling
- Accounting period locks
- Advanced reporting enhancements

---

# COMPLETED

Phase 1 – Security Hardening
Phase 2 – Production Hardening
Phase 3A – Financial Integrity Layer 1 & 2

---

# NEXT PHASE (Planned)

Phase 3B – Credit Note System (Proper Integration)
- Model
- Migration
- Posting service
- UI endpoint
- Audit logging

Phase 3C – Reconciliation Dashboard
- Stripe vs Internal comparison
- Invoice balance diagnostics

---

# FUTURE PHASES

Phase 4 – Monitoring & Observability Expansion
Phase 5 – UX Premium Polish
Phase 6 – Client Portal Expansion
Phase 7 – Desktop Sync Reintegration

---

Current focus: Stabilize financial core before expansion.


## Phase 3D
- Credit Note UI (create + post)
- Invoice edit integration


## Phase 3E
- Credit note UI hardening + money formatting + numbering


## Phase 3F
- Credit note edit (draft-only)
- Dollar input UX
- Invoice activity timeline


## Phase 3G
- Backup & recovery pack: ez360_backup command + retention settings + restore runbook
- Soft-delete guardrails (SyncModel.delete defaults to tombstone)


### Phase 3H — Monitoring & Observability (DONE)
- Sentry optional integration
- /healthz DB health endpoint
- request ids + slow request logging
- webhook + email failure logging


### Phase 3I - UX & Premium Experience (DONE)
- Dashboard onboarding checklist with progress + next-step CTA.
- Dismissible alert messaging with safer tag mapping.


Next recommended hardening priorities:
- Customer credit auto-apply engine (rules + visibility) to reduce A/R friction.
- Accounting period locks to prevent back-dated changes.
- Advanced reporting enhancements (cashflow, utilization, job-costing).

### Phase 3J+ — Subscription Tiers & Feature Gating (DONE)
- Updated subscription model to Starter/Professional/Premium + Monthly/Annual.
- Added extra seat quantity support (included seats + add-on seats).
- Implemented `tier_required` decorator and centralized feature gating rules.
- Gated Accounting to Professional+ and Dropbox Integration to Premium (future feature).
- Updated Stripe checkout + webhook sync to use plan/interval + infer add-on seats.

## Phase 3K — Ops Console (DONE)
- Staff-only Ops Console (/ops/) with company search + quick Support Mode entry.
- Add follow-ups later: deeper subscription debugging (Stripe IDs), event/audit timeline, and “impersonate user” workflow with explicit banners + audit log.


## Completed – Phase 3M (Refund Linkage)
- Payment refunds: data model, UI entry point, balance recalculation, and accounting reversal entries.
- Next: accounting period locks + advanced reporting enhancements.


## Phase 3N — Accounting Period Locks (DONE)
- Added AccountingPeriod model and UI to create/close periods.
- Enforced closed-period rules across journals/invoices/payments/expenses.
- Professional+ tier; Admin+ role.


## Phase 3O — Advanced Reporting Enhancements (DONE)
- Added CSV export (?format=csv) for core accounting reports.
- Added Premium report: Project Profitability (journal-based, by project) with CSV export.

## Phase 3P — Launch Readiness Checks (DONE)
- Added staff-only Launch Checks page under Ops Console.
- Added `python manage.py ez360_check` management command for deploy validation (non-zero exit on errors).

## Next (Phase 3Q)
- Notification/alert hooks for critical ops events (stripe webhook failures, failed backups, repeated 500s) and retention for ops logs.
