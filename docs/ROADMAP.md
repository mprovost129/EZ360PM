# EZ360PM Roadmap (Locked After Phase 3A Layer 2)


## Current Hardening Track (Phase 3F → Launch)

### Completed
- **3F** Financial integrity + credit notes + reconciliation (baseline)
- **3G** Backup & Recovery (DB dump + optional media + retention + soft-delete guardrails)
- **3H** Monitoring & Observability (healthz, request-id, slow request logging, optional Sentry)
- **3I** UX polish (onboarding checklist, dismissible alerts, cleanup)
- **3J** Client Credit Ledger + Auto-Apply Credit
- **3K** Ops Console + Support Mode (staff-only)
- **3L** Ops Timeline + Stripe Subscription Diagnostics (staff-only)
- **3M** Refund Linkage (refunds tied to payments/invoices; balance + journal recalcs)
- **3N** Accounting Period Locks (Professional+; admin+; enforcement)
- **3O** Advanced Reporting Enhancements
- **3P** Launch Readiness Checks (staff-only UI + ez360_check command)
- **3Q** Ops Retention & Pruning (staff-only UI + ez360_prune command)
- **3R** Security Defaults (production-on email verification gate, secure cookies/HSTS/SSL defaults, default company 2FA policy)
- **3S** Financial Integrity + Invoice Reconciliation (manager+)
- **3T** Ops Alerts + Session Hardening (admin alerts on webhook/email failure; session key rotation on login)
- **3U** UX Perf Polish: pagination across major lists + CSP rollout fix (report-only toggle + jsDelivr allowlist)
- **3V** Performance indexing (Payments + client credit tables)
- **3W** Lightweight perf checks + Docs/TimeEntry indexes
- **3X** Settings profiles fix (dev/prod separation restored)
- **3Y** Dev HTTP/HTTPS usability fix
- **4A** Observability (healthz + Sentry init + env docs)
- **4B** Ops alerts expansion + perf sampling to DB
- **5A** UX premium: Getting started page + nav progress
- **6D** S3 direct uploads + project file workflow (presigned POST to private bucket)
- **6E** UI polish (state dropdown styling, project label display), currency input UX for Project rates, and timer dropdown in navbar
- **6G** Ops SLO dashboard (active users via presence pings) + optional external ops alert webhook notifications
- **6G1** Render migration hotfix (billing index rename idempotent + create-if-missing)
- **6H** Ops: PII export (company CSV ZIP) + SLO webhook freshness metrics
- **6I** Security: enforce 2FA for Admin/Owner roles (step-up confirmation on company-scoped pages + login flow supports 2FA)
- **6J** Production staticfiles hardening (WhiteNoise + hashed/compressed static; fixes Render admin/app CSS)
- **6K1** Mobile topbar fix + Sentry init (responsive logo sizing, safe-area insets; Sentry init enabled when DSN set)

### Next (Planned)
- **Backup & Recovery Gate**: automated DB backups on Render, retention policy verified, and a documented restore test.
- **Monitoring Gate**: confirm Sentry capture in production + add an ops “test error” button for staff.
- Optional: move CSP from report-only to enforced after validating allowlist.

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

## Phase 3Q — Ops Retention + Alerts (DONE)
- Added retention policy + pruning tooling (CLI + Ops UI).
- Added ops report runner for alert-style emails.

## Phase 3R — Security Defaults (DONE)
- Production-on defaults for email verification + secure cookies/SSL/HSTS (env overridable).
- Production default for 2FA requirement for admin/manager roles (env overridable).

## Phase 3S — Financial Integrity + Reconciliation (DONE)
- Added invoice reconciliation view and “recalculate” affordance.
- Hardened journal posting immutability and balance checks.

## Phase 3T — Ops Alerts + Session Hardening (DONE)
- Best-effort admin alerts for webhook/email failures (production-on defaults).
- Session key rotation on password login.

## Phase 3U — Pagination + CSP (DONE)
- Shared pagination helper + UI applied across major list pages.
- Fixed CSP settings typing and added env toggles; report-only defaults in production.

## Phase 3V — Performance Indexing (DONE)
- Added missing DB indexes for Payments + Client Credit ledger/application tables.
- Fixed `ClientCreditApplication` index declaration (was not in Meta; indexes were not being created).

## Phase 3W — Perf Sanity Checks + Documents/TimeEntry Indexes (DONE)
- Added dev-only per-request perf logging middleware (slow requests + slow ORM queries; env-driven thresholds).
- Added `python manage.py perf_check` management command for repeatable queryset benchmarks.
- Added Postgres partial indexes for Documents and TimeEntry list filters (ignoring soft-deleted rows).

## Phase 3X — Settings Profiles Fix (DONE)
- Restored clean settings layering (base/dev/prod) so local dev remains reliable.
- Removed base→dev import shim behavior and hard-coded hosts.
- Centralized DEBUG-derived defaults in `apply_runtime_defaults()` and re-run in dev/prod after setting DEBUG.

## Phase 3Y — Dev HTTP/HTTPS Access Fix (DONE)
- Dev no longer gets forced into HTTPS redirects due to production-style env values.
- `config/settings/dev.py` defaults to HTTP access and supports explicit local HTTPS testing via `DEV_SECURE_SSL_REDIRECT=1`.

## Next hardening items (after Phase 3S)

- [ ] Add links to Reconciliation from invoice detail screen (UI affordance).
- [ ] Add staff-only “Create correcting journal entry” tooling (optional v1, but useful).
- [ ] Expand data integrity: block edits to invoices/line-items after SENT, except controlled actions (void, credit note, refunds).
- [ ] Add lightweight performance checks (query counts on dashboard/report pages).

## Next hardening items (after Phase 3Y)

- [ ] Review Projects + Clients list filters and add indexes if needed (based on actual queryset usage).
- [ ] Add a small set of targeted prefetch/select_related improvements for any remaining N+1 hotspots found by perf logs.
- [ ] Consider Postgres trigram search (optional) if search boxes become a real perf hotspot.

- [x] Phase 4A — Monitoring & Observability
  - [x] Add `/healthz/` endpoint with DB + cache checks
  - [x] Add Sentry wiring (env-driven, safe import) for dev/staging/prod
  - [x] Complete `.env.example` with all required env vars

Next (Phase 4B):

- [x] Phase 4B — Ops Alerts + Perf Sampling (DB-backed)
  - [x] Staff-only Ops Alerts page (open/resolved, filters, search, resolve)
  - [x] DB alerts for Stripe webhook failures + email send failures
  - [x] Optional slow-request sampling stored to DB (env-driven)

Next (Phase 4C):
- [x] Add rate-limit and abuse dashboards (top throttles, 2FA/verify failures, repeated bad login) (staff-only).
- [x] Add “system status” widget on Ops Console (healthz last check, Sentry DSN presence, email backend mode).



- 5B Sensible defaults + empty states (DONE)

- [x] Phase 6A — Launch readiness gate UI + smoke test (DONE)


## Phase 6B — Completed (2026-02-13)

- Invoice lock enforcement (model + line items + view guard + UI banner)
- Ops reconciliation console (staff-only)
- Smoke test includes immutability verification
- Minor bug fixes (payments audit prev_balance; accounting ValidationError import)

### Next suggested: Phase 6C
- Refund/adjustment guardrails (partial refunds + journal postings) and Stripe idempotency checks
- Basic “unapplied payments” admin tooling (apply/void) to clear reconciliation drift

## Phase 7A — Release Discipline (DONE)

- [x] Add `/version/` endpoint for safe build metadata.
- [x] Add build metadata env vars (APP_ENVIRONMENT, BUILD_VERSION, BUILD_SHA, BUILD_DATE) and document them.
- [x] Launch checks warn in production if build metadata is missing.
- [x] Add `python manage.py ez360_preflight` for CI/staging/prod pre-deploy verification.


## Phase 7B — Release Notes + Preflight Migration Guard (DONE)
- Ops page for release notes + build metadata visibility.
- Preflight fails when pending migrations exist (default).


- [x] Phase 7C — Correlated logging + production security checks (launch checks)


### Phase 6D — Backup automation command (DONE)
- `ez360_backup_db` management command + env documentation.

## Hardening – Backup & Recovery
- [x] Wire backup/prune commands into host scheduler (cron/Render job) for daily backups + weekly prune.
- [x] Record a restore test (Ops → Backups or `ez360_record_restore_test`) after the first production backup is taken.
- [ ] Optional: add S3 backup target (Phase 6G) if host snapshots are insufficient.


## 2026-02-13 — Completed: Phase 6C (Drift Toolkit + S3 Multi-Bucket)
- Ops Drift Toolkit + remediation actions (recalc, post-missing, link payment).
- S3 multi-bucket support (public/private).

## 2026-02-13 — Completed: Phase 6C.1 (Private downloads)
- Private bucket downloads now use presigned URLs (configurable expiry) and are routed through permission-gated app endpoints.
- Expenses now include a receipt “paperclip” action to open the attached receipt securely.

### Next: Phase 6E — Storage visibility + cleanup
- Ops → Storage page: show S3 config health, buckets, locations, and a "test upload"/"test download" check.
- Optional: lifecycle/retention policies for private bucket (host-level) + report guidance.
- Optional: direct-upload support for additional attachments (documents, proposals) if needed.

## 2026-02-14 — Completed: Phase 6F (Services catalog + timer pause/resume)
- Project Services now use CatalogItem(Service) dropdowns with optional custom names.
- Navbar timer displays project + live elapsed and supports pause/resume.

## 2026-02-15 — Completed: Phase 6K2 (Timer dropdown fix + locked invoice UX)
- Timer dropdown no longer relies on Bootstrap dropdown JS; uses deterministic local toggle logic.
- Locked invoices render read-only (disabled fields/line-items + no Save) to match financial invariants.

## 2026-02-14 — Completed: Phase 6F.2 (Error page resiliency)
- Added `templates/_public_shell.html` shim so 404/500 pages render in production.

### Next: Phase 6G — Service Catalog UI + timer-to-invoice workflow
- Add an in-app (non-admin) Service Catalog screen (CRUD, active toggle).
- Add “Allocate time by service” editor on time entry detail (splitting minutes across services).
- Add “Convert time to invoice line items” mapping service→rate + description.

## Done (2026-02-14)

- Render migration hotfix: billing 0003 index rename/create now idempotent.
- Error page stability: `_public_shell.html` shim + 404/500 link fixes (no `dashboard:` namespace dependency).
- Email verification resend: fixed URL ordering + login requirement + ops alert on failures.

## Next

- Phase 4 (Monitoring & Observability): verify Sentry wiring in production, validate Ops alerts for **email** + **webhooks**, and add a small “send test email” button in Ops to confirm provider config end-to-end.
- Phase 5 (UX polish): standardize remaining form select styling + money widgets across invoices/estimates/expenses.

## Next (immediate)
- **Phase 6E (Storage visibility):** Ops → Storage health page + “test presign/upload/download” button.
- **Phase 6L (Security headers):** confirm CSP + HSTS settings in production and add a Launch Check that validates static assets + admin CSS loads.

## Next UI shell items
- Apply theme tokens to buttons/badges across all templates (replace hardcoded `btn-dark` where appropriate).
- Add “collapsed sidebar” (icon-only) option for desktop if needed.
- Add per-user preference storage in DB (future) to sync theme across devices.
