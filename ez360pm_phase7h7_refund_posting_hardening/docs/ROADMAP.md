## 2026-02-16 — Phase 7H6 (DONE)
- Timer persistence: stop no longer clears project/service/note.
- Added “Clear selections” action for timer (navbar + timer page).
- Fixed `can_manage_catalog` context availability for timer UI.

## 2026-02-16 — Phase 7H7 (NEXT)
- Idempotency scan: ensure every posting source sets `JournalEntry.source_type/source_id` and never double-posts.
- Add Admin “Ops Checks” page to run smoke + invariants commands from the UI (staff-only).
- Expand timer persistence: remember last selection even if TimerState row is recreated (fallback defaults per employee).

## 2026-02-16 — 2026-02-16 — Phase 7H4 (Ops-grade invariants + admin polish)
**Done:**
- Admin money formatting completed for: CRM Clients, Payables (Bills/Line Items/Payments/Recurring Plans), Payments (credits, applications, refunds), Accounting journal line inlines.
- Invariants expanded:
  - Payments/refunds sanity
  - JournalEntry provenance sanity (source_type requires source_id)
- Timer UI: added “Manage catalog services” link (Manager+).

**Next (Phase 7H5):**
- Expand invariants further:
  - invoice net paid vs refunds
  - credit ledger vs applications vs effective balance
  - posting idempotency cross-checks (document/payment/expense unique source entries)
- Finish remaining admin polish:
  - Expenses admin money columns
  - Credit ledger and refund filters/search improvements
- Timer UX: persist last selections across stop/start (confirm TimerState fields are kept) and add “Open project” shortcut.

## 2026-02-16 — Phase 7G5 (Money UX normalization for Projects & Documents)
**Done:**
- Projects + Documents money fields migrated to `MoneyCentsField` (dollars UI, cents storage).
- Fixed `|money` template filter alias so dashboards and lists render correctly.

**Next (Phase 7H):**
- Expand money UX standard across remaining modules (invoices summary, reports, payables edge cases).
- Strengthen invariants + smoke tests:
  - document totals match line items (subtotal/tax/total)
  - project billing rates correct across create/edit
- Time tracking UX hardening:
  - navbar timer: add “service on the fly” (creates CatalogItem) and persist last selections.
- Ops:
  - add a `manage.py readiness_check` command for env + migrations + storage + email sanity.

## 2026-02-15 — Phase 7G complete
**Done:**
- Unified private download/open link behavior across receipts, project files, and bill attachments via shared helper (`core/services/private_media.py`).
- Added optional inline preview for PDFs/images using presigned S3 URLs (`?preview=1`), plus UI Preview buttons where applicable.

**Next:**
- Phase 7H: A/P payments workflow expansion (checks / vendor credits) if matching QuickBooks parity.
- Phase 7I: tighten financial audit trails around payables (payment posting, void/reversal workflows) and reporting parity.



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
- **6O2** Clients pagination hotfix (guarded previous/next page evaluation)
- **6P** Monitoring gate: Ops Probes (Sentry test error + test alert) + launch check evidence
- **6R1** UI/Perf hardening: invoice reconciliation CTA + staff clients subquery optimization
- **6S** 2FA policy optional (admin-configurable only) + Projects performance indexes (assignee/client/updated)
- **7A** Accounts Payable foundation (new payables app: Vendors, Bills, Bill Payments, auto-posting)
- **7B** Vendor unification + vendor ledger + dashboard payables widget
- **7C** A/P Aging report (UI+CSV) + Bill attachments (direct-to-S3 private keys)
- **7D** Secure bill attachment downloads (presigned GET) + UI download action

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
- [x] Optional: add S3 backup target (DONE 2026-02-15) if host snapshots are insufficient.


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
- **Phase 6M (Email diagnostics):** Ops “Send test email” button + Launch Check for SMTP/provider config + webhook success.

## Next UI shell items
- Apply theme tokens to buttons/badges across all templates (replace hardcoded `btn-dark` where appropriate).
- Add “collapsed sidebar” (icon-only) option for desktop if needed.
- Add per-user preference storage in DB (future) to sync theme across devices.

## 2026-02-15 — Completed: Phase 6M1 (Launch Checks expansion + static hardening verification)
- Expanded Ops → Launch Checks with WhiteNoise/static verification (middleware + manifest strict).
- Added smoke-level data presence checks (company/client/project/invoice/payment) to confirm end-to-end exercise in the current environment.
- Kept checks lightweight (settings/env + minimal DB existence queries).

## 2026-02-15 — Completed: Phase 6N (Ops Email Diagnostics)
- Added Ops → Email test page (staff-only) to send a real test email and record SENT/FAILED results.
- Failures create an Ops Alert (EMAIL / ERROR) for visibility.
- Launch Checks now include DEFAULT_FROM_EMAIL validation + “recent successful email test” evidence check.

## 2026-02-15 — Completed: Phase 6O.1 (Error page hardening)
- 404/500 templates no longer depend on unstable namespaces; link to stable `home` route.
- Error handlers are defensive to prevent template failures from causing recursive 500s.
- Error pages display Request ID when available for support correlation.

## 2026-02-15 — Completed: Phase 6O.2 (Pagination crash fix)
- Fixed template-time `EmptyPage` exceptions caused by unguarded `previous_page_number()` / `next_page_number()` calls.
- Shared pagination include now guards page-number methods behind `has_previous/has_next`.
- Audit events list pagination hardened the same way.

### Next: Phase 6O — UI reliability polish (mobile + dropdowns)
- Make sidebar + topbar interactions consistent across iOS/Android/desktop (offcanvas + dropdowns + safe areas).
- Audit all navbar dropdowns for Bootstrap-JS independence (match the timer’s deterministic toggle).
- Apply EZ360PM theme tokens to remaining forms/buttons for a more cohesive look.


## 2026-02-15 — Pack: Optional 2FA enforcement + Client email index
- Completed: 2FA enforcement policy change (admin-configurable only).
- Completed: CRM client email index + migration for import/search performance.


## Completed (2026-02-15)

- Phase 6N+ Hotfix: Added `documents:numbering` URL alias to prevent NoReverseMatch on Getting Started.

## 2026-02-15 — Completed: Phase 6O.3 (UI reliability polish — sidebar/company dropdown)

- Sidebar now prevents body scroll when open on mobile (`body.no-scroll`) and closes automatically on nav click.
- Added resize handler to close sidebar/actions when switching to desktop breakpoint.
- Company switcher dropdown is now Bootstrap-independent (deterministic toggle) and themed (`btn-outline-ez`).


## 2026-02-15 — Phase 6O.4: Accessibility polish
- Added skip-to-content link and focus-visible styling.
- Improved keyboard behavior for custom dropdown toggles.

### Phase 6T — Accounts Payable (MVP) ✅
**Goal:** Basic QuickBooks-like bills + vendor tracking with accounting postings.
- Vendors: list/create/edit (company-scoped).
- Bills: draft/create/edit, line items, post (locks), list + status filters.
- Payments: record payments against posted bills.
- Accounting integration: auto-post journal entries for bill posting + bill payments.

### Next (proposed) — Phase 6U
- A/P polish: vendor statements, bill attachments (receipts), recurring bills.
- Payment batching: "Pay bills" screen (select multiple bills), check printing export.
- Aging report for A/P (by vendor, due buckets).


## 2026-02-15 — Next: Payables Phase 7B/7C
- Add A/P Aging report page + export (CSV) and link from Reports.
- Add Bills 'due soon' quick filter and status chips.
- Add Vendor → New Bill shortcut + vendor filter on Bills list.
- Add bill attachment support (S3 private) if required (optional).

### Payables (Accounts Payable) — Next
- Add **Bill attachment downloads** (presigned GET) + optional in-app preview for PDFs/images.
- Add **Vendor 1099 tracking** (vendor type, tax ID storage w/ PII guardrails).
- Add **Recurring bills** (templates + schedule) and bulk posting.
- Expand reporting: cashflow view, spend by vendor/category.

### 2026-02-15 — Phase 7G.1 (Done)
- [x] Fix `/projects/new/` 500: register `catalog.CatalogItem` in Django Admin so `admin:catalog_catalogitem_changelist` resolves.

## 2026-02-15 — Phase 7G1 (Manual skeleton + Help Center routing fix)
**Done:**
- Wired Help Center + Legal URLs into root routing (`helpcenter.urls` now included).
- Updated app top-nav Help icon to open the Help Center.

**Next (corporate-grade hardening & polish):**
1) **Manual + QA**
   - Expand `docs/FEATURE_INVENTORY.md` into full “User Manual + QA Plan”.
   - Add acceptance checks per feature and role.
2) **UX consistency**
   - Enforce `$xx.xx` formatting for all money inputs (forms + templates + admin displays).
   - Normalize select inputs (state dropdown, service selectors) to match Bootstrap styling.
   - Ensure timer dropdown supports project→service→notes and removes redundant client selection.
3) **Catalog as first-class**
   - Add in-app CRUD UI for Catalog Items (Manager/Admin), plus safe search and “add service on the fly”.
4) **Time tracking correctness**
   - Make TimeEntry project-driven (derive client from project; prevent mismatched client/project).
   - Expand approval workflow checks (who can approve, editing rules after approval/billing).
5) **Email deliverability + templates**
   - Standardize transactional email templates (brand header/footer, accessibility, plain-text fallback).
   - Verify SMTP/provider config and bounce handling.
6) **Ops readiness**
   - Add a “production readiness” checklist command (static checks, migrations sanity, required env vars).
   - Add structured logging for request_id across modules.
   - Add backup/restore drill doc + automated DB dump hooks (if not already).
7) **Security posture**
   - Confirm 2FA is optional but fully enforceable via company settings.
   - Ensure rate-limits on login, password reset, and public endpoints.
   - Confirm CSRF/secure cookie flags per environment.

## 2026-02-15 — Phase 7G2 (Corporate polish: Catalog UI + TimeEntry project-driven + money formatting)
**Done:**
- Added in-app **Catalog** (Manager+) with list/search/filter + create/edit/delete.
- Added global money formatting helper (`money_cents` template filter) and money parsing helpers.
- Payment forms now use Decimal-safe dollars→cents conversion and show $ placeholders.
- Time tracking now enforces **project-driven client** (client is derived from project; mismatch blocked).

**Next (Phase 7G3 candidates):**
1) Apply money formatting + $ input UX to **all** money surfaces:
   - Project hourly/flat rates, invoice line items, expenses, bills, COA/journals readouts.
2) Tighten TimeEntry state rules:
   - Lock edits after Approved/Billed; enforce approve/bill permissions; add manager approval UI.
3) Catalog “add on the fly”:
   - From timer + from invoice line item picker.
4) Smoke test expansion:
   - Add invariants for posting idempotency, A/R aging math, partial payments/credits.


## 2026-02-16 — Phase 7H1 (DONE) — Money UX completion + smoke-test alignment

**Done**
- Expenses/Payables/Payments forms migrated to `MoneyCentsField` (cents storage, dollars UI).
- Templates updated for `$` input groups and correct field names.
- Smoke test aligned to project-driven time-entry policy.

**Next (Phase 7H2)**
- Finish money UX + formatting across reporting, dashboards, and any remaining list views/admin columns.
- Expand invariants: document totals, tax totals, balance math; payment/credit invariants; posting idempotency.
- Timer UX: “service on the fly”, persist last project/service selection per user.


## 2026-02-16 — Phase 7H2 (DONE) — Invariants + refund form + money UX polish

**Done**
- Fixed missing `PaymentRefundForm` referenced by `payments.views` (refund UI no longer crashes).
- Added `manage.py ez360_invariants_check` to validate core invoice/payment invariants (totals, paid/balance sanity, succeeded payments bounds).
- Polished money-entry UX in document line item tables (unit price + tax now use `$` input-groups).
- Removed “debug cents” display from Credit Note post confirmation screen.

**Done (Phase 7H3)**
- Expand invariants: credits/credit-notes effective balance, posting idempotency, GL integrity checks.
- Add timer “service on the fly” (create/select CatalogItem directly from the timer dropdown).
- Standardize money formatting in admin list displays and dashboards (use `|money` everywhere).

**Next (Phase 7H4)**
- Finish admin money formatting (Expenses, Payables, Credit Notes, Refunds) and remove any remaining raw cents UI.
- Add stronger invariants: credit ledger vs applications, refunds vs paid snapshots, posting idempotency scan.
- Timer UX: persist last project/service/note and add quick link to manage Catalog.

## 2026-02-16 — Phase 7H4 (DONE) — Admin money polish + refund/journal invariants + timer link

**Done**
- Completed admin money formatting across operator-critical models (no raw cents in admin list displays).
- Expanded `ez360_invariants_check` for refund sanity and JournalEntry provenance checks.
- Added “Manage catalog services” quick link in timer UI for Manager+.

**Next (Phase 7H5)**
- Expand invariants to cover client credit ledger vs rollup, credit applications sanity, and net-payment math (amount - refunded).
- Fix any structural issues inside `ez360_invariants_check` and make output reliable (no indentation/flow bugs).
- Add idempotency cross-checks where possible (journal uniqueness / provenance).


## 2026-02-16 — Phase 7H5 (DONE) — Invariants suite reliability + client credit sanity + journal balance checks

**Done**
- Rewrote `manage.py ez360_invariants_check` for correctness and readability:
  - Invoice totals + paid/balance sanity
  - Net payments = amount - refunded checks
  - Client credit ledger sum vs `Client.credit_cents` rollup warnings
  - Credit application integrity checks (positive cents; invoice/company/client matching)
  - Payment refunds sanity checks
  - JournalEntry balance checks (debits == credits) + provenance enforcement
- Added `--quiet` option for CI-style runs.

**Next**
- Extend invariants to validate:
  - per-invoice applied credits never exceed available credit at time of application (requires snapshotting policy or sequential rebuild)
  - posting idempotency mapping across invoices/payments/expenses (source_type/source_id coverage audit)
- Timer persistence: remember last project/service/note per employee (DB-backed).
