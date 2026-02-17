## 2026-02-16 — Phase 7H44 (DONE)
- Statements: added **Send now (filtered set)** bulk action (confirmation + safety cap) in Statement Reminders queue.
- Statements: added per-client statement activity tracking (last viewed/last emailed) and surfaced on a new Client Detail page.
- Ops: added `company_id` filter to Ops Alerts and updated Ops Dashboard deep links to preserve company scope.

## 2026-02-16 — Phase 7H45 (DONE)
- Help Center: ensured screenshot assets are present and ready for swapping once UI is stable.
- Statements: added contextual Help links on Statement page + Statement Reminders + Client Detail.

## Next (Phase 7H46)
- Help Center: swap placeholder screenshots with final screenshots once UI is stable.
- Statements: consider adding statement activity to Client list columns (optional) and exposing last sent/last viewed on Statement page.
- Ops: add quick-pick snooze durations + show active snooze state on Ops Dashboard grouping.


## 2026-02-16 — Phase 7H29 (DONE)
- Daily ops checks now create Ops Alerts + optional admin emails on failures.
- Added Help Center content for Profit & Loss, Balance Sheet, Trial Balance + contextual report Help buttons.

## 2026-02-16 — Phase 7H30 (DONE)

- Added Client Statements (open invoices) with CSV export and optional PDF export (WeasyPrint if installed).
- Added statement email send (templated) from Statement page.
- Help Center: role-based workflow guidance + screenshot placeholders for Time/Invoices/Accounting/Statements.
- Ops: DB-backed alert routing (email/webhook) with staff UI + Ops Dashboard recent alerts list.


## Phase 7H31 — Statements polish + Ops deep links + Template sweep (DONE)

- Template sweep: fixed remaining `{% url %}` un-namespaced usage (404/500) and removed invalid parentheses in `{% if %}` blocks.
- Statements polish:
  - Added optional date-range filter (issue date; falls back to created date when issue date missing).
  - CSV/PDF exports honor the same date range.
  - Statement email now includes an optional “View statement” link back into the app (requires `APP_BASE_URL`).
  - PDF includes optional period + “View online” link (requires `APP_BASE_URL`).
- Ops:
  - Added per-alert detail page and deep links from Ops Dashboard recent alerts list.
  - Added “Send test alert” panel on Ops Dashboard to exercise routing.
  - Added new alert source `ops_dashboard`.
- Help Center:
  - Replaced screenshot placeholder text with actual placeholder images under `static/images/helpcenter/` (ready to swap with real screenshots).

## Phase 7H32 — Statement PDF/email hardening + readiness + Ops copy JSON (DONE)

- Statements:
  - Added optional “Attach PDF” checkbox for statement emails (WeasyPrint-only).
  - Improved statement PDF styling for print (Letter sizing, margins, page numbers, cleaner header/table layout).
  - Fixed statement PDF/email redirect flows and querystring handling.
- Readiness:
  - Added `APP_BASE_URL` check (warns when blank with DEBUG=False) so email deep links are reliable.
- Ops:
  - Added alert detail links in the Ops Alerts list table.
  - Added “Copy JSON” button on alert detail page.
- Help Center:
  - Screenshot placeholders remain in place; next phase will swap in real screenshots.

## Phase 7H33 — Statement email preview + PDF error hints + Ops JSON download + Help screenshots (DONE)

- Statements:
  - Added **Email preview** modal on Client Statement page (renders HTML + text preview via JSON endpoint; no email is sent).
  - Improved PDF failure messages to differentiate **WeasyPrint missing** vs **render/deps failure** (Cairo/Pango hints).
- Ops:
  - Added **Details JSON download** endpoint (`details.json`) from Alert Detail.
  - Added **Request ID correlation** display when present in alert details with one-click copy.
- Help Center:
  - Began swapping screenshot placeholders for richer placeholder images for **Time Tracking**, **Invoices/Payments**, and **Statements**.

## Phase 7H34 — Help Center Accounting screenshots + Statement inline warnings + Ops alert filter affordances (DONE)

- Help Center: replaced remaining Accounting screenshot text with placeholder screenshot cards (Chart of Accounts, Journal Entries, Reports, General Ledger) and removed all "[Screenshot: ...]" text blocks.
- Statements: added inline warning banner on the Statement page when `APP_BASE_URL` is missing and/or WeasyPrint is not installed.
- Ops: made alert KPI cards clickable quick-filters (open + source) while preserving querystring-based filters.

## Phase 7H35 — Ops alert pagination + bulk resolve + statement recipient defaults + finance help permissions (DONE)

- Ops Alerts:
  - Added server-side pagination (50/page).
  - Added bulk resolve (selected IDs or filtered up to 500).
- Statements:
  - Added “Send test to myself” action.
  - Persisted last-used statement recipient per client (per company) and prefill it next time.
- Help Center:
  - Added permissions table to core finance/reporting pages.

## Phase 7H36 — Statement reminders + Ops noise filters + alert pruning (DONE)

- Statements/Collections: added **StatementReminder** scheduling hook (schedule/cancel per-client reminders) + management command `ez360_send_statement_reminders`.
- Ops: added **noise filters** (ignore path prefixes / user-agent tokens) and wired them into alert creation (best-effort).
- Ops: added **alert pruning** management command `ez360_prune_ops_alerts` for resolved alerts older than N days (default from Ops SiteConfig).


## Phase 7H37 — Scheduling guidance + Statement reminder presets (DONE)

- Help Center: expanded Production runbook scheduling section with Render cron recommendations for:
  - `ez360_run_ops_checks_daily`
  - `ez360_send_statement_reminders`
  - `ez360_prune_ops_check_runs`
  - `ez360_prune_ops_alerts`
- Statements: added reminder tone presets (Friendly nudge vs Past due) and corresponding email templates.

## Phase 7H38 — Ops cron guidance + Statement cadence helper (DONE)

- Ops: added copy/paste **Render cron job** guidance + link on Ops Checks page.
- Statements: added reminder **cadence helper** (quick-pick dates) and displayed **last sent reminders** on the Statement page.
- Help Center: placeholder screenshots remain until post-launch (real screenshots task deferred).

## Next (Phase 7H39)

## Phase 7H39 — Reminder attempt visibility + failed reschedule + Ops scheduler sanity (DONE)

- Statements/Reminders:
  - Added `attempted_at` + `attempt_count` fields to `StatementReminder` so failures have clear “last attempt” metadata.
  - Reminder sender command now records an attempt timestamp/counter even on failures.
  - Statement page now shows a **Failed attempts** table (with last error) and a **one-click reschedule** action.
- Ops:
  - Ops Dashboard now includes copy/paste cron commands (same list as Ops Checks).
  - Added scheduler/env sanity warnings (APP_BASE_URL + email backend/SMTP placeholder checks).
- Help Center:
  - No content changes in this phase (still pending real screenshots once UI is stable).

## Phase 7H40 — Statement retry UX + scheduler readiness expansion (DONE)

- Statements:
  - Failed reminders table now includes an optional **reschedule-to-date** input (defaults to +7d if blank).
  - Added **Retry now** (staff-only) action for a single failed reminder (synchronous send + attempt tracking).
- Ops:
  - Extended scheduler/env sanity warnings to include **Stripe**, **S3/storage**, **backup storage**, and **domain alignment** checks.
- Help Center:
  - Screenshot placeholders remain until post-launch; begin swapping once UI is stable.

## Phase 7H41 — Statement audit trail + copy email + Ops alert dedup/snooze (DONE)

- Statements:
  - Added per-reminder **audit trail** (Scheduled by / Updated by + timestamp) on the Statement page.
  - Added **“Email me a copy”** option for statement sends (best-effort copy to acting user).
- Ops:
  - Added **alert deduplication window** (SiteConfig `ops_alert_dedup_minutes`).
  - Added **snooze** for alerts (OpsAlertSnooze + UI action from alert detail).
- Help Center:
  - Screenshot replacement is still pending; will be done after UI stabilizes.

## Phase 7H42 — Statement tone preview + Reminder bulk actions + Ops export/quick snooze (DONE)

- Statements:
  - Statement email send now supports selecting **Tone**: Standard / Friendly nudge / Past due.
  - Statement email preview modal now previews the selected **Tone** (HTML + text) before sending.
  - Reminder scheduler includes a **Preview reminder email** action (uses the selected tone + optional PDF attachment).
  - Added company-wide **Statement Reminders** queue with bulk actions:
    - Cancel selected
    - Reschedule selected
- Ops:
  - Alerts list now shows **dedup_count** ("Dup" column) when alerts were deduplicated.
  - Added **quick snooze** dropdown from the alerts list (30m / 2h / 1d).
  - Added **Export CSV** for unresolved alerts (respects filters; capped).
- Help Center:
  - Prepared wiring for swapping placeholder images; actual screenshots pending UI stabilization.

## Phase 7H43 — Reminder bulk send-now + delivery report + Ops grouping summary (DONE)

- Statements:
  - Added **bulk “Send now”** action for selected reminders (staff/admin-only).
  - Added **Reminder delivery report** (last 30 days: sent/failed by day) to the reminders queue.
- Ops:
  - Added **Open alerts summary** grouped by **source** and **source+company** for fast triage.
- Help Center:
  - Screenshot swapping remains pending until we capture real UI screenshots post-freeze.

## Phase 7H44 — Filtered send-now + client statement history + ops company filter (DONE)

- Statements:
  - Add “send now” for **filtered set** (not just selected) with safety cap + confirm checkbox.
  - Add per-client statement history (last sent / last viewed) on client detail.
- Ops:
  - Add company filter to Ops Alerts list (company_id) and preserve it in links.
  - Add source/company snooze from the grouping summary.
- Help Center:
  - Replace placeholder images with real screenshots for the top workflows (Invoices, Time, Projects).

## Phase 7H20 — Template/Static sanity + Readiness staticfiles (DONE)

- Template sanity command fixed and expanded (money/static tag load checks, invalid-if parentheses warning).
- Readiness check expanded to validate `STATIC_ROOT` existence and writability (prod gate).

## Phase 7H21 — URL sanity check + Ops wiring (DONE)

- Added management command `ez360_url_sanity_check` to validate `{% url %}` names referenced in templates (best-effort).
- Added Ops → Checks checkbox to run URL sanity and store evidence.
- Fixed Ops forms indentation regression and migrated drift forms to UUID company IDs.

## Phase 7H23 — Help Center fill + Template sanity expansion + Ops evidence export (DONE)

- Template sanity scan expanded:
  - Warn on POST forms missing `{% csrf_token %}`.
  - Warn on `{% url %}` tags using un-namespaced view names (heuristic).
- Help Center pages added:
  - Recurring Bills
  - Refunds
  - Ops Console
- Ops Checks: added “Export recent runs” ZIP bundle (includes runs.csv + per-run output files).

## Phase 7H24 — URL arg-count heuristics + Contextual Help deep links + Ops daily scheduler + retention (DONE)

- Expanded `ez360_url_sanity_check` to (best-effort) validate positional argument counts for the top 20 most-used `{% url %}` tags and warn on obvious mismatches.
- Added contextual Help deep links:
  - Payables → Recurring bills now links to Help Center → Recurring Bills.
  - Payments → Payment/Refund screen links to Help Center → Refunds.
  - Payables → Bill detail includes Help Center → Accounting link.
- Added scheduler/retention commands:
  - `python manage.py ez360_run_ops_checks_daily` (persist OpsCheckRun evidence; intended for daily cron/scheduler)
  - `python manage.py ez360_prune_ops_check_runs --days 30` (Ops evidence retention)
- Help Center → Ops Console updated with automated daily checks guidance.

## Phase 7H25 — Ops actions + URL sanity kwargs + Help Center A/P (DONE)

- Ops → Checks: added buttons for "Run daily checks now" and "Prune ops runs" (staff-only).
- URL sanity: added best-effort kwarg validation and namespaced-variant warnings for un-namespaced url names.
- Help Center: added Bills (A/P), Vendor Credits, and A/P Reconciliation pages and linked them from Help Home.


## Phase 7H26 — Help Center A/R + contextual help (DONE)

- Help Center: added Accounts Receivable, Client Credits, and A/R Aging pages and wired them into Help Home and Help sidebar navigation.
- Reports: Accounts Aging report now includes a contextual Help button (Help Center → A/R Aging).

## Phase 7H27 — Help Center A/R workflows + A/P Aging help + Production runbook (DONE)

- Help Center: added Collections, Statements, and Report interpretation pages for A/R workflows.
- Help Center: added A/P Aging page; A/P Aging report now has a contextual Help button.
- Help Center: added Production runbook (deploy + daily ops + scheduling notes).

### Next (Phase 7H28)
- Expand “Statements” into an exportable PDF/email workflow (optional) and add a lightweight client statement view.
- Add Help Center content for P&L / Balance Sheet / Trial Balance pages with screenshots/definitions.
- Add optional Ops alert routing (email + webhook) for failing daily checks.


## 2026-02-16 — Phase 7H15 (DONE)
- Ops Console: fix seat limit display by computing seats limit via `seats_limit_for()`.

**Next:**
- Continue launch hardening: fill Help Center content, finalize email templates/subjects, expand invariants & readiness evidence, and run end-to-end ops checks on staging/prod.

## 2026-02-16 — Phase 7H7 (DONE)
- Payment refund posting hardening: missing `Sum` import fixed.
- Refund proration math moved to integer-safe allocation (no float drift).

## 2026-02-16 — Phase 7H8 (DONE)
- Timer persistence expanded: last timer selections now persist in `TimeTrackingSettings` and rehydrate if `TimerState` is recreated.
- Added staff-only Ops Checks UI (/ops/checks/) to run: smoke test, invariants, idempotency scan.
- Added `ez360_idempotency_scan` management command to detect missing/duplicate journal provenance (NULL-safe).

## 2026-02-16 — Phase 7H9 (NEXT)
- Posting provenance audit: ensure every auto-posting source sets `JournalEntry.source_type/source_id` consistently.
- Extend Ops Checks page with “Company picker” + recent run history.
- Add CI-friendly flags to ops checks (quiet/fail-fast) and wire to launch evidence.

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

### Phase 7H9 — Readiness Gate + Ops UI (DONE)
- Add `ez360_readiness_check` management command (env/db/migrations/storage/email) and surface it in Ops → Checks (staff-only).
- Capture output for launch evidence and reduce reliance on CLI access.

### Phase 7H10 — Email Professionalization + Help Context (NEXT)
- Add branded transactional email base templates (HTML + text) and standard subjects.
- Add “Help” contextual links on key pages (Invoices, Payments, Bills, Time) to reduce support burden.
- Add minimal email “preview” dev endpoint (staff-only) for template QA.

## 2026-02-16 — Phase 7H11 (DONE)
- Ops Checks UI: added Company picker, Quiet + Fail-fast options.
- Added OpsCheckRun history model + admin. Ops Checks page now shows recent runs with output.
- Ops Checks now persists run history for launch evidence (best-effort).

## 2026-02-16 — Phase 7H12 (NEXT)
- Posting provenance audit: ensure every auto-posting source sets JournalEntry.source_type/source_id.
- Ops Checks: add “pin run to release” (link to ReleaseNote) and export evidence bundle.
- Email professionalization: consistent subjects + reply-to + list headers, and template lint.

## 2026-02-16 — Phase 7H12 (DONE)
- Timer UX: added "Open selected project" shortcut in timer dropdown and timer page.
- Small corporate UX polish in time workflow.

## 2026-02-16 — Phase 7H13 (DONE)
- Money display unification: legacy `|cents_to_dollars` now matches corporate `$x,xxx.xx` output.
- Preferred currency filter is `|money` and key surfaces were updated to use it.

## 2026-02-16 — Phase 7H14 (NEXT)
- Email polish: standardize all transactional email subjects, add plain-text fallbacks where missing, and ensure consistent support contact and company branding.
- Help Center content: fill core articles (Getting Started, Time Tracking, Invoices & Payments, Bills & AP, Reports) with concrete, role-based instructions.
- Expand Ops Checks: add download/export of run output for launch evidence (CSV/text) and cap stored output size with truncation notice.

## 2026-02-16 — Phase 7H15 (DONE)
- Ops dashboard seat-limit crash fixed (computed seat limits via `seats_limit_for`).

## 2026-02-16 — Phase 7H16 (DONE)
- Recurring bills list: load `money` filter and add contextual Help link.

## 2026-02-16 — Phase 7H17 (DONE)
- Fixed Ops dashboard NoReverseMatch by updating Ops company routes to use UUID converters.
- Ops company detail/timeline/resync endpoints now accept `<uuid:company_id>`.

## Next (Phase 7H18)
- Template sweep: ensure any template using `|money` loads `{% load money %}` (prevent regressions).
- Expand Help Center Accounting content (Bills/Recurring Bills/Payments workflows).
- Ops: add company ID display/copy button and improve company search/filtering.

## 2026-02-16 — Phase 7H19
**DONE**
- Fix Ops Checks indentation error (ops/views.py) blocking app startup.
- Improve template sanity check coverage for money filters.

**NEXT**
- Continue template sanity sweeps (reverse/url/tag loads) and add checks for other common tag libraries.

## 2026-02-16 — Phase 7H22
**DONE**
- Ops Checks: added **Run all** option (runs all checks; skips Smoke Test when no company selected).
- App navigation: added **Help Center** link in sidebar.
- Help Center: expanded home “topic tiles” for core workflows.

**NEXT (Phase 7H23)**
- Help Center: deepen each article with role-based step-by-step instructions (time approvals, invoicing, credits/refunds, bills/recurring bills) + screenshots placeholders.
- Ops Checks: add one-click “Run recommended” preset (launch evidence default set).
- Template sanity: also warn on `{% url %}` without quotes, and missing `{% load humanize %}` where used.