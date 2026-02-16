## 2026-02-16 — Phase 7H20 (Template/Static sanity + Readiness staticfiles)

**Shipped:**
- Fixed `ez360_template_sanity_check` regex and expanded checks:
  - Flags templates using `|money` / `|money_cents` without `{% load money %}` (FAIL).
  - Warns on `{% static %}` usage without `{% load static %}`.
  - Warns on parentheses inside `{% if %}` tags (common Django template break).
- Expanded `ez360_readiness_check` to validate staticfiles configuration:
  - In prod (`DEBUG=False`), fails if `STATIC_ROOT` is missing or does not exist (collectstatic not run).
  - Validates `STATIC_ROOT` is writable for local filesystem cases.

**Why:**
- Prevent repeat “template gotcha” regressions and catch missing tag loads early.
- Corporate deployments must treat staticfiles readiness as a launch gate.

## 2026-02-16 — Phase 7H15 (Ops subscription seat limit fix)
**Shipped:**
- Fixed Ops Console crash: `CompanySubscription` has no `seats_limit` attribute.
- Ops dashboards now compute seat limits via `billing.services.seats_limit_for(subscription)`.

**Notes:**
- This avoids N+1 queries and matches the subscription enforcement logic used elsewhere.

## 2026-02-16 — Phase 7H8 (Ops checks + idempotency scan + timer defaults)
**Shipped:**
- Added staff-only **Ops Checks** page (`/ops/checks/`) to run:
  - `ez360_smoke_test`
  - `ez360_invariants_check`
  - `ez360_idempotency_scan`
- Added `ez360_idempotency_scan` command to detect missing/duplicate journal provenance (NULL-safe uniqueness).
- Timer selections now persist in `TimeTrackingSettings` (`last_project`, `last_service_*`, `last_note`) and are used to rehydrate `TimerState` if it’s recreated.

**Why:**
- Corporate-grade ops requires UI access to evidence-producing checks.
- TimerState is a OneToOne row and can be recreated; defaults guarantee user continuity.

**Next:**
- Provenance audit across all posting sources to guarantee every auto-post sets `JournalEntry.source_type/source_id`.
- Add run history for Ops Checks (who/when/output summary).

## 2026-02-16 — Phase 7H6 (Timer persistence + clear action)
**Shipped:**
- Timer now **remembers last project/service/note** after stopping (no longer clears selections).
- Added **Clear selections** action (POST) for users to reset timer fields intentionally.
- Fixed timer templates/context so `can_manage_catalog` is consistently available (navbar + timer page).

**Why:**
- Corporate UX expectation: frequent time tracking should not require re-selecting the same project/service repeatedly.

**Next:**
- Persist last-used selection defaults into a lightweight per-employee preference record (optional if we keep using TimerState as the source of truth).
- Extend invariants to cover posting idempotency across all posting sources and surface failures in Admin “Ops Checks”.

## 2026-02-16 — Phase 7H4 (Admin money + invariants + timer catalog link)
**Shipped:**
- Fixed remaining admin money displays in CRM, Payables, Payments, and Accounting (no raw cents shown).
- Expanded `ez360_invariants_check` to validate refund sanity and journal provenance.
- Timer UI now includes a quick link to manage catalog services (Manager+).

**Notes:**
- Refund invariants validate `refunded_cents` range and compare to sum of succeeded refunds (warn on mismatch for legacy rows).

## 2026-02-16 — Phase 7G5 (Money UX normalization for Projects & Documents)

**Done:**
- Standardized money inputs to **dollars in the UI** while storing **integer cents** in the database using `core.forms.money.MoneyCentsField`.
- Projects:
  - `ProjectForm` now edits `hourly_rate_cents` and `flat_fee_cents` directly via `MoneyCentsField` (no float/Decimal drift).
  - Updated `templates/projects/project_form.html` to match new field names.
- Documents:
  - `LineItemForm` now edits `unit_price_cents` and `tax_cents` via `MoneyCentsField`.
  - Fixed line total computations to use cents inputs.
  - Updated `templates/documents/document_edit.html` to match new field names.
- Templates:
  - Added `money` filter alias (same as `money_cents`) in `core/templatetags/money.py` so existing `|money` usage renders correctly.

**Notes / follow-ups:**
- Continue rolling the same money UX standard across any remaining modules still using ad-hoc Decimal “*_dollars” helpers.
- Add/expand invariant tests to ensure no cents↔dollars regressions in document totals and project billing rates.

## 2026-02-15 — Phase 7G (Unified private media access + previews)
**Done:**
- Implemented shared private-media access helper: `core/services/private_media.py`
  - Normalizes storage keys (handles storage.location prefixes).
  - Generates presigned **download** URLs (attachment) and **preview** URLs (inline) for PDFs/images.
  - Centralizes content-type guessing and previewability rules.
- Added S3 presign helper for inline preview: `core.s3_presign.presign_private_view()`.
- Updated private-media open endpoints to use shared helper (consistent behavior across modules):
  - Expense receipts: `expenses:expense_receipt_open` supports `?preview=1`
  - Project files: `projects:project_file_open` supports `?preview=1`
  - Bill attachments: `payables:bill_attachment_download` supports `?preview=1`
- Added template filter `previewable` (`core/templatetags/file_extras.py`) and UI links:
  - Bills: Preview button shown for previewable attachments
  - Project files: Preview button shown for previewable non-Dropbox files
  - Expenses: Preview button shown for previewable receipts

**Notes / Behavior:**
- Preview is only enabled for PDFs and common image types; otherwise links fall back to download.
- Authorization remains enforced by existing module views; we do not expose raw bucket URLs in templates.

**Next:**
- Phase 7H: expand A/P payments workflow (checks / vendor credits / payment batches) if pursuing QuickBooks parity, plus reconciliation UI updates.


## 2026-02-15 — Phase 7F (Recurring Bills / A/P)
**Done:**
- Added `payables.RecurringBillPlan` with frequency (weekly/monthly/yearly), `next_run`, `is_active`, optional `auto_post`, vendor, expense account, and amount.
- Manager UI under Payables:
  - Recurring bills list
  - Create / Edit / Delete
  - **Run now** button to generate a bill immediately and advance the schedule.
- Added recurring bill engine:
  - `payables/services_recurring.py` with safe date math (month rollovers) and schedule advancement.
  - Management command: `python manage.py run_recurring_bills [--company <uuid>]` to generate all due bills (next_run <= today).
- Sidebar updated: “Recurring bills” under Payables.

**Notes / Behavior:**
- Each run generates a new Bill with a single line item (expense account + amount) and recalculates totals.
- If `auto_post` is enabled, the generated bill is posted immediately.
- Schedule advancement uses safe month/year rollover rules.

**Next:**
- Phase 7G: continue payables parity (expanded A/P payments workflow, credits/checks) and improve idempotency/traceability of recurring runs if needed.


## 2026-02-15 — Phase 7E: Private media delete-on-remove + Project file open/delete
- Added best-effort S3 object deletes when removing bill attachments and project files (configurable).
- Implemented missing project file open/delete views and wired project files UI actions.
- Added S3_DELETE_ON_REMOVE setting (default true) to control deletion behavior.


# EZ360PM — Project Snapshot

## Snapshot 2026-02-13 — Phase 6D (S3 Direct Uploads + Project File Workflow)

### Shipped
- Implemented presigned POST direct uploads to **private S3 bucket** for:
  - Expense receipts
  - Project files
- Added `storage` app endpoint: `POST /api/v1/storage/presign/` (Manager+ only).
- Added settings/env vars:
  - `S3_DIRECT_UPLOADS`
  - `S3_PRESIGN_EXPIRE_SECONDS`
  - `S3_PRESIGN_MAX_SIZE_MB`
- Project file upload now supports `file_s3_key` (multipart file optional when direct uploads enabled).

### Notes
- Templates already use the direct-upload flow when `USE_S3=1` and `S3_DIRECT_UPLOADS=1`.

## Snapshot 2026-02-14 — Phase 6E (UI Polish + Timer Navbar + Dollar Inputs)

### Shipped
- **CRM**: Client “State” now uses consistent Bootstrap select styling (matches the rest of the form).
- **Projects**:
  - Project `__str__` now renders as `P-00001 · Project Name` (fixes “Project object …” dropdown labels across the app).
  - Hourly rate + flat fee are now entered in **dollars** (`$xx.xx`) and converted to cents internally.
- **Time Tracking**:
  - Timer is now accessible from the **top navbar** as a dropdown (start/stop + project + service + notes).
  - Timer start no longer asks for both client + project; **client is derived from the selected project**.
  - Timer stop now creates an optional single service row consuming the full duration (when selected/typed).

## Snapshot 2026-02-14 — Phase 6G (Ops SLO Dashboard + Presence Pings + Optional Alert Webhook)

### Shipped
- Added lightweight **User Presence** tracking (best-effort, throttled per session) to support staff SLO visibility.
  - Middleware: `core.middleware.UserPresenceMiddleware` (writes at most once per minute per session).
  - Model: `ops.UserPresence` keyed by `(user, company)` with `last_seen`.
- Added staff-only **SLO Dashboard** in Ops:
  - `/ops/slo/` showing active users (5m/30m), open alert counts (webhook/email/auth), and per-company active user breakdown.
- Added optional **external webhook notification** for ops alerts:
  - Env: `OPS_ALERT_WEBHOOK_URL` (best-effort POST JSON)

## Snapshot 2026-02-15 — Phase 6J (Production Staticfiles Hardening)

### Shipped
- Added **WhiteNoise** to serve `/static/` reliably in production (Render), including Django Admin assets.
- Switched static storage to `CompressedManifestStaticFilesStorage` for hashed + compressed assets.
- Added env var `WHITENOISE_MANIFEST_STRICT` (default 1) for emergency recovery if `collectstatic` does not run.
  - Env: `OPS_ALERT_WEBHOOK_TIMEOUT_SECONDS`

## Snapshot 2026-02-15 — Phase 6L (S3 Backup Target + Backup Freshness Launch Check)

### Shipped
- Added optional **S3 backup target** for database dumps:
  - Env: `BACKUP_STORAGE=s3`, `BACKUP_S3_BUCKET`, `BACKUP_S3_PREFIX`
  - `ez360_backup_db` uploads the generated `.sql.gz` to S3 and records bucket/key/sha256 in `BackupRun.details`.
  - `ez360_prune_backups --storage s3` prunes old S3 backup objects using the same retention rules.
- Ops → Backups now supports staff-only **Run backup now** and **Prune old backups** buttons.
- Launch Checks now include **Recent successful backup recorded** (required only when `BACKUP_ENABLED=1`).

### Notes
- S3 backup upload uses `boto3` (added to requirements).
- Ops Alerts are raised automatically when a backup run fails (best-effort).

## Snapshot 2026-02-14 — Hotfix (Render migration: Billing index rename)

### Shipped
- Fixed production migration failure on Render:
  - Error: `relation "billing_com_plan_int_status_idx" does not exist`
  - Cause: `migrations.RenameIndex(...)` fails hard when the *old* index name is missing.
- Updated `billing/migrations/0003_...` to be **idempotent** using `SeparateDatabaseAndState`:
  - DB operation uses `RunSQL` with `to_regclass(...)` guards:
    - Renames old→new only when old exists and new doesn’t.
    - Creates the expected indexes if neither exists.
  - State operation preserves `RenameIndex` so Django’s migration graph stays consistent.

## Snapshot 2026-02-13 — Phase 3U (UX Perf Polish: Pagination + CSP)

### Shipped
- Standardized list pagination via `core.pagination.paginate` and applied it to:
  - Clients, Projects, Documents, Payments, Expenses, Merchants, Time Entries, Team.

## Snapshot 2026-02-15 — Phase 6O2 (Pagination Crash Fix After CSV Import)

### Shipped
- Fixed a production 500 on `/clients/` caused by templates evaluating `page_obj.previous_page_number` / `next_page_number` even when the pager UI was disabled.
  - Django raises `EmptyPage: That page number is less than 1` when `previous_page_number()` is called on page 1.
- Hardened shared pagination include (`templates/includes/pagination.html`) to only resolve page-number methods when `page_obj.has_previous/has_next`.
- Hardened Audit event list pagination similarly.

### Result
- Client list (and any view using the shared pagination include) renders reliably on first/last pages.
- Added shared pagination UI partial: `templates/includes/pagination.html`.
- Added querystring helper template tag: `{% qs_replace %}` in `core.templatetags.querystring`.

### Security / CSP fix
- Fixed CSP configuration so it correctly works with `core.middleware.SecurityHeadersMiddleware`:
  - `SECURE_CSP` is now the policy (dict/string), and `SECURE_CSP_REPORT_ONLY` is a **bool**.
  - Added env flags:
    - `EZ360_CSP_ENABLED` (default ON in production)
    - `EZ360_CSP_REPORT_ONLY` (default ON in production; turn OFF to enforce)
- Updated policy allowlist to support Bootstrap + Icons via jsDelivr CDN.

### Notes
- The Clients list header “Showing X clients” is now page-scoped (X = current page rows) rather than a global count.

## Snapshot 2026-02-13 — Phase 3R (Security Defaults)

### Shipped
- Email verification gate is now **default ON in production** (DEBUG=False) unless explicitly overridden via `ACCOUNTS_REQUIRE_EMAIL_VERIFICATION`.
- Production security defaults are now **default ON in production** unless overridden:
  - `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`.
- New company onboarding defaults to **require 2FA for managers/admins/owners** in production (override via `COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS`).

### Notes
- Local/dev remains relaxed by default (DEBUG=True), but you can flip any behavior via env vars.


## Snapshot 2026-02-13 — Phase 3J (Client Credit Ledger + Auto-Apply)

**Baseline:** user-provided ZIP `de775a36-ff2c-4581-9bbd-1725e308de24.zip`.

### Shipped
- Client credit **application** flow (apply stored client credit to invoices).
- New model `payments.ClientCreditApplication` with indexes and admin registration.
- Invoice stored balance recompute now accounts for:
  - successful payments
  - posted credit notes (A/R applied)
  - applied client credits (credit applications)
- Credit notes that generate **customer credit** now also create a credit ledger entry (+delta) and sync client rollup.
- Invoice edit page now shows:
  - Client Credit card (available credit + apply form)
  - Credit notes table using dollar formatting
- Accounting posting for credit applications: DR Customer Credits / CR A/R (idempotent).

### Notes
- Rollup `Client.credit_cents` is treated as a cached value; ledger is source of truth.

Snapshot Date: 2026-02-13
Baseline: ez360pm_phase3a_layer2.zip

---

# ✅ Completed Phases

## Phase 1 – Security Hardening
- Email verification gate after login
- 2FA enforcement scaffolding (role-based)
- Progressive account lockout
- Security headers middleware
- Support mode (audited, read-only)

## Phase 2 – Production Hardening
- HTTPS enforcement
- Secure cookies (Lax, HttpOnly)
- Stripe environment separation
- Health endpoint
- Backup command scaffolding
- Monitoring toggles (Sentry-ready)

## Phase 3A – Financial Integrity (Layer 1 & 2 ONLY)
- Journal repost prevention (no mutation after initial post)
- Invoice financial field lock after SENT
- Line item lock after SENT
- Status downgrade protection
- Paid invoices fully immutable

---

# ❌ NOT IMPLEMENTED (Intentionally Rolled Back)

- CreditNote model (not production-integrated)
- Reconciliation dashboard
- Balance recalculation refactor
- Journal reversal workflow
- Admin UI financial locking polish

---

# Current Status

EZ360PM now enforces:
- Financial immutability on invoices
- No journal mutation
- Safe status transitions

Accounting core is protected.
Advanced corrective workflows pending.



## 2026-02-13 — Phase 3B Stage 1 (Proper)
- Fixed Phase 3A implementation defects (added real model-level invoice immutability + journal freeze).
- Added CreditNote model (Draft/Posted) + admin registration.
- Added migration merge for dual 0004 documents migrations + CreditNote migration.


## 2026-02-13 — Phase 3G (Backup & Recovery)
- Added `ez360_backup` management command (Postgres dump + optional media archive) with retention pruning.
- Added soft-delete guardrails: default deletes on SyncModel subclasses are tombstones unless `hard=True`.
- Added runbook: `docs/BACKUP_RECOVERY.md`.


## 2026-02-13 — Phase 3H (Monitoring & Observability)
- Added DB-verified health endpoint (`/healthz`), request IDs, and slow-request logging.
- Added optional Sentry integration (safe if dependency missing).
- Improved error logging around Stripe webhooks and email delivery.
- Added runbook: `docs/MONITORING.md`.


## 2026-02-13 — Phase 3I (UX & Premium Experience)
- Dashboard upgraded to a **guided onboarding checklist** (progress bar + "Next" CTA) based on live company data.
- Alerts upgraded to dismissible Bootstrap alerts; Django's `error` tag maps to `danger`.
- Fixed an internal defect introduced in Phase 3G: removed duplicate `soft_delete` method definition.

- 2026-02-13: Added CreditNote posting service (Draft → Posted) with immutable JournalEntry creation and audited event logging.
- Admin action: Post selected credit notes.


## Phase 3C (implemented)
- 2026-02-13: Credit note allocation fields added (AR applied vs customer credit).
- 2026-02-13: Payment recalculation now subtracts posted credit notes for balance_due_cents, while invoice status remains payment-driven.
- 2026-02-13: Accounting reconciliation dashboard added (/accounting/reconciliation/).

- 2026-02-13: Phase 3D added Credit Note UI (create draft + post), invoice edit credit note section, and admin read-only locks.

- 2026-02-13: Phase 3E tightened credit note permissions, added safer invoice gating (must be SENT+), money formatting via cents_to_dollars, reconciliation link, and credit note numbering sequence CN-YYYYMM-####.

- 2026-02-13: Phase 3F added draft-only credit note edit UI, dollar-based inputs, invoice activity timeline (audit events), and improved invoice edit credit note interactions.

- 2026-02-13: Phase 3F added draft-only credit note edit view, dollars-based credit note form (store cents internally), invoice timeline (audit events), and stronger UI clarity.

- 2026-02-13: Phase 3G added backup & recovery tooling: `ez360_backup` management command (Postgres pg_dump + optional media tarball), retention pruning settings (EZ360_BACKUP_DIR/RETENTION_DAYS/KEEP_LAST), and documented restore procedure in docs/BACKUP_RECOVERY.md. Also added soft-delete guardrail by making SyncModel.delete() default to tombstoning via deleted_at.


## Phase 3H (Monitoring & Observability Pack) — Completed
- Added request id middleware (X-Request-ID).
- Added /healthz endpoint (DB-verified) and updated legacy /health/ to match.
- Added slow request logging with env threshold.
- Added optional Sentry integration in production settings (safe if dependency absent).
- Improved webhook + email failure logging (and Sentry capture when available).
- Added docs/MONITORING.md and updated ENV_VARS.md.

## 2026-02-13 — Phase 3J+ (Subscription Tiers + Feature Gating)

- Updated subscription tiers to match Stripe plan model:
  - Starter ($19/mo or $190/yr) — 1 included seat
  - Professional ($49/mo or $490/yr) — 5 included seats (includes Accounting engine)
  - Premium ($99/mo or $990/yr) — 10 included seats (advanced reporting, future API/Dropbox)
  - Extra seats add-on ($10/mo or $100/yr per seat) tracked as subscription item quantity.
- Implemented tier-aware gating:
  - `billing.decorators.tier_required(min_plan)` decorator.
  - `billing.services.plan_allows_feature(feature_code)` centralized feature rules.
- Enforced tier gating in the app:
  - Accounting module is Professional+.
  - Dropbox Integration module is Premium-only (pre-wired for future rollout).
- Stripe integration updated for the new tier model:
  - Checkout expects (plan + billing interval) instead of plan+seat-tier.
  - Webhook sync best-effort infers plan/interval/extra_seats from subscription metadata and/or price lookup_keys.
- Billing UI updated:
  - Plan = Starter/Professional/Premium + Monthly/Annual
  - Seat limit computed as included + extra seats

## 2026-02-13 — Phase 3K: Ops Console + Support Mode UX
- Added new internal staff-only Ops Console at /ops/ with company search, subscription overview, seat counts, and company detail view.
- Ops Console can enter Support Mode for a target company and sets active company in session.
- Sidebar now shows Staff section (Ops Console + Support Mode) for is_staff users.


## 2026-02-13 — Phase 3L (Ops Timeline + Subscription Diagnostics)
- Added staff-only company timeline view combining Audit events + Stripe webhook processing events.
- Added staff-only “Resync from Stripe” action (fetch subscription from Stripe API and sync CompanySubscription).
- Ops company detail now shows best-effort matched recent webhook events for the company.
- Added Stripe fetch+sync helper in billing.stripe_service (uses Stripe API; requires STRIPE_SECRET_KEY + stripe package).

## 2026-02-13 — Hotfix: Ops Support Mode import
- Fixed ops.views import/call to use core.support_mode.set_support_mode (previously referenced non-existent enable_support_mode).


## Phase 3M – Refund Linkage (Payments)
- Added PaymentRefund model + admin.
- Added refund workflow: manager can create a refund (Stripe best-effort) from payment edit screen.
- Refunds roll up into Payment.refunded_cents and adjust invoice balances (net payments).
- Accounting: added payment_refund journal entries reversing cash/AR/credits based on original payment allocation.


- 2026-02-13: Phase 3O advanced reporting: CSV exports for accounting reports + Premium Project Profitability report.

## 2026-02-13 — Phase 3P: Launch Readiness Checks
- Added staff-only Launch Checks page (Ops) that runs a lightweight production checklist (security, Stripe, email, static, Sentry optional).
- Added management command: `python manage.py ez360_check` (non-zero exit if errors).
- Added sidebar link (Staff → Launch Checks).

## 2026-02-13 — Phase 3Q: Ops Retention & Pruning
- Added env-driven retention controls:
  - `EZ360_AUDIT_RETENTION_DAYS` (default 365)
  - `EZ360_STRIPE_WEBHOOK_RETENTION_DAYS` (default 90)
- Added management command: `python manage.py ez360_prune` (dry-run by default; use `--execute` to delete).
- Added staff-only Ops page: /ops/retention/ with prune-now button and dry-run eligible counts.

## 2026-02-13 — Phase 3S (Financial Integrity + Reconciliation)

- Added **Invoice Reconciliation** page to help diagnose invoice balances (payments, refunds, credit notes, client credit applications) and provide a one-click **Recalculate** action.
- Hardened accounting journaling: journal lines are now **write-once** (no mutation once posted) and entries must be balanced.
- Fixed `DocumentLineItem.__str__` placement (was a stray global function).

## 2026-02-13 — Phase 3T: Ops Alerts + Session Hardening

- Added best-effort ops alert emails for **Stripe webhook** failures and **email** delivery failures (controlled by env defaults ON in production).
- Added session key rotation on successful password login.
- Added `core.ops_alerts.alert_admins()` helper.

## 2026-02-13 — Phase 3U: Pagination + CSP

- Added shared pagination helpers (helper, querystring tag, pagination partial) and applied pagination across major list pages.
- Fixed CSP settings typing and added rollout toggles (report-only defaults in production).

## 2026-02-13 — Phase 3V: Performance Indexing

- Added missing DB indexes for Payments and client credit ledger/application tables.
- Fixed `ClientCreditApplication` index declaration (previously not in Meta; indexes were not being created).

## 2026-02-13 — Phase 3W: Lightweight Perf Checks + Documents/TimeEntry Indexes

- Added dev-only **PerformanceLoggingMiddleware** (logs slow requests + slow ORM queries; thresholds are env-driven).
- Added `python manage.py perf_check` management command to run and time the core list querysets for **Documents** and **TimeEntry**, reporting query counts and slowest SQL.
- Added Postgres partial indexes (ignoring soft-deleted rows) to speed up common list filters:
  - Documents: (company, doc_type, created_at) and (company, doc_type, status, created_at) where deleted_at IS NULL
  - TimeEntry: (company, status, started_at), (company, employee, status, started_at), (company, billable, started_at) where deleted_at IS NULL

## 2026-02-13 — Phase 3X: Settings Profiles Fix (Dev/Prod Separation)

- Fixed a settings architecture issue that made **dev mode unreliable**:
  - Removed an accidental “settings shim” behavior from `config/settings/base.py` that was importing `dev` inside `base` and overriding values.
  - Removed hard-coded `ALLOWED_HOSTS` that forced production hosts even in local dev.
- Re-established the intended pattern:
  - `base.py` contains shared settings only.
  - `dev.py` and `prod.py` override environment-specific behavior.
- Added `apply_runtime_defaults()` in `base.py` for settings derived from `DEBUG` (email verification defaults, security cookie defaults, CSP rollout defaults, etc.).
  - `dev.py`/`prod.py` now re-run it after setting `DEBUG` so defaults stay consistent.
- Cleaned up `prod.py` duplicate/invalid logging definition and fixed the formatter string.

## 2026-02-13 — Phase 3Y: Dev HTTP/HTTPS Access Fix

- Fixed a dev usability issue where local development could be forced into HTTPS redirects due to production-style env values.
- `config/settings/dev.py` now defaults to **HTTP** (no SSL redirect) regardless of `SECURE_SSL_REDIRECT` in the environment.
- Optional local HTTPS testing is now explicit via `DEV_SECURE_SSL_REDIRECT=1` (requires an HTTPS-capable local server).

## 2026-02-13 — Phase 4A: Monitoring & Observability

Phase 4A — Monitoring & Observability

- Added public health check endpoint: `GET /healthz/` (includes DB + cache checks).
- Centralized Sentry initialization via `init_sentry_if_configured()` in `config/settings/base.py` and called from `dev.py` and `prod.py`.
- Updated `.env.example` to be a complete, copy/paste-ready reference for all required environment variables (dev + prod), including Phase 4 monitoring vars.

## 2026-02-13 — Phase 4B: Ops Alerts + Perf Sampling (DB-backed)

- Added DB-backed ops alerts (`ops.OpsAlertEvent`) with a staff-only **Ops Alerts** page:
  - Filters by status (open/resolved), source, level, and search.
  - Acknowledge/resolve workflow.
  - Quick KPIs for open webhook/email/perf alerts.
- Stripe webhook failures now generate DB alerts (signature invalid and processing exceptions) in addition to best-effort admin email alerts.
- Email send failures now generate DB alerts (in addition to optional admin email alerts + Sentry capture).
- Performance logging middleware can optionally store sampled **slow request** alerts to the DB (no SQL stored), controlled via env/settings:
  - `EZ360_PERF_LOGGING_ENABLED`
  - `EZ360_PERF_REQUEST_MS`
  - `EZ360_PERF_SAMPLE_RATE`
  - `EZ360_PERF_STORE_DB`

## 2026-02-13 — Phase 5A: UX & Premium Experience (Getting Started)

- Added a dedicated **Getting started** page (`/getting-started/`) with the computed onboarding checklist + quick actions.
- Added a **Getting started** link to the left sidebar with a progress badge when setup is incomplete.
- Added a lightweight onboarding progress computation to the global app context (uses `.exists()` checks).


## 2026-02-13 — Phase 5B: UX defaults + empty states
- Added Company financial defaults (invoice due days, estimate valid days, sales tax percent guidance, default taxable checkbox).
- On company onboarding, provisioned defaults: numbering scheme, minimal chart of accounts, and default document templates.
- Document wizard now sets sensible default dates (issue date + due/valid dates).
- Document line item form defaults Taxable checkbox using company default.
- Improved list-page empty states (clients, projects, documents, time, payments) with clear actions.


## 2026-02-13 — Phase 6A: Launch Readiness Gate + Ops Security
- Added Ops **Security** page (staff-only): recent account lockouts + auth/throttle ops alerts.
- Added Ops **Launch Gate** checklist (staff-managed) with seed items matching the hardening outline.
- Added `python manage.py ez360_smoke_test --company-id <id>` command to validate the end-to-end flow in dev/staging (DB-only, no Stripe).
- Added ops alert hooks:
  - Throttle blocks create Ops alerts (source=throttle).
  - Login blocked due to lockout creates Ops alerts (source=auth).


## Phase 6B — Invoice immutability hardening + reconciliation console (2026-02-13)

- Strengthened **invoice immutability**:
  - Invoices are now considered **locked** once **Sent**, **Partially Paid**, **Paid**, or if any **payments / client credit applications / posted credit notes** exist.
  - Locked invoices reject changes to: client/project, dates, and all money fields (subtotal/tax/total).
  - Locked invoices reject **line item create/update/delete** (including soft-delete).
  - Added `InvoiceLockedError` for explicit failures.
  - UI: invoice edit page shows a clear “Invoice locked” banner; POST edits are blocked at the view layer too.

- Added **Ops → Reconciliation** page (staff-only):
  - Company selector + snapshot metrics for invoices/payments/credits.
  - Practical flags: AR vs invoice balances, customer credits vs credit ledger, payments vs invoice paid drift.
  - Shows accounting account balances (AR 1100, Cash 1000, Customer Credits 2200) when accounting is enabled.

- Fixed a real bug in payment audit logging:
  - `prev_balance` was referenced before assignment in `apply_payment_and_recalc`; now captured correctly.

- Smoke test upgraded:
  - `python manage.py ez360_smoke_test --company-id <id>` now validates that locked invoices reject document and line-item mutations.

Files touched (high level):
- `documents/models.py`, `documents/views.py`, `templates/documents/document_edit.html`
- `ops/views.py`, `ops/urls.py`, `ops/services_reconciliation.py`, `templates/ops/reconciliation.html`, `templates/ops/dashboard.html`
- `payments/services.py`
- `core/management/commands/ez360_smoke_test.py`
- `accounting/models.py` (missing ValidationError import)

## 2026-02-13 — Phase 6C: Backups/Restore Visibility + Recording (Ops)
- Added Ops → Backups page for configuration visibility and recording backup runs + restore tests.
- Added BackupRun and BackupRestoreTest models (staff/audit use).
- Added BACKUP_* env vars (safe defaults; dev forces disabled unless DEV_BACKUP_ENABLED).

## 2026-02-13 — Phase 7A: Release Discipline (Build Metadata + Preflight)
- Added public `GET /version/` endpoint returning safe build info (environment/version/sha/date).
- Added build metadata settings: APP_ENVIRONMENT, BUILD_VERSION, BUILD_SHA, BUILD_DATE.
- Launch checks now warn in production if build metadata is missing.
- Added management command `python manage.py ez360_preflight` (Django checks + launch checks) for CI/staging/prod.
- Updated `.env.example` to include build/release variables.


## 2026-02-13 — Phase 7B: Release Notes + Preflight Migration Guard
- Added Ops → Releases page with staff-maintained release notes tied to build metadata.
- Added ReleaseNote model + admin registration.
- Enhanced ez360_preflight to detect pending migrations and fail (configurable via PREFLIGHT_REQUIRE_NO_PENDING_MIGRATIONS).


## 2026-02-13 — Phase 7C: Request-ID logging + production security checks
- Added request-id aware base LOGGING with `core.logging.RequestIDLogFilter` and standard console formatter.
- Updated prod logging to inherit base and include key app loggers.
- Added launch checks for secure cookies and HSTS (warn-level; dev-safe).


## 2026-02-13 — Phase 6D: Backup Automation Command

- Added `python manage.py ez360_backup_db` to run `pg_dump` backups (Postgres only) and record `ops.BackupRun` success/failure.
- Added env vars: `EZ360_PG_DUMP_PATH` (optional), plus documented backup flags in `.env.example`.
- Dev remains safe: backups are disabled unless enabled via env (`BACKUP_ENABLED=1` or `DEV_BACKUP_ENABLED=1`).

## Phase 3E / 6E – Backup retention pruning (command)
- Added `python manage.py ez360_prune_backups` to enforce retention by age and optional max-count.
- Added env var `BACKUP_MAX_FILES` and documented it.
- This complements `ez360_backup_db` and the Ops Backups evidence UI.


## 2026-02-13 — Phase 6F: Backup scheduling guidance + restore-test helper
- Added `python manage.py ez360_record_restore_test` to record restore test evidence from CLI.
- Documented host scheduling (cron/Task Scheduler) for `ez360_backup_db` + `ez360_prune_backups`.
- Updated backups Ops UI with scheduler guidance.


## 2026-02-13 — Soft-delete guardrails + optional S3 media storage

- **Soft-delete guardrails**: `SyncModel` now uses a default manager that hides `deleted_at` rows (`objects`) and exposes `all_objects` for admin/maintenance.
  - Added `SyncQuerySet.delete()` bulk soft-delete guardrail.
  - Admins now include soft-deleted rows via `IncludeSoftDeletedAdminMixin` (Documents, Payments/Credits, Clients/Vendors, Projects, Time Entries).
- **Media storage strategy**: added optional S3/S3-compatible media storage configuration via `STORAGES` + `USE_S3` env var (requires `django-storages[boto3]` when enabled).
  - Added docs: `docs/MEDIA_STORAGE.md`
  - Updated `.env.example` and `docs/ENV_VARS.md`



## 2026-02-13 — Phase 6C: Reconciliation Drift Toolkit + S3 Multi-Bucket Storage
- Added Ops Drift Toolkit (/ops/drift/) with staff actions: recalc invoice rollups, post missing accounting entries, and link orphan payment → invoice.
- Implemented S3 multi-bucket media storage via core.storages: public bucket (logos/general) + private bucket (receipts/project files).
- Updated .env.example, ENV_VARS, MEDIA_STORAGE docs.


## 2026-02-13 — Phase 6C.1: Private downloads (signed URLs) + receipt download route
- Private media (receipts/project files) now uses **presigned S3 URLs** via `PrivateMediaStorage(querystring_auth=True)`.
- Added `expenses:expense_receipt_open` route to gate receipt access and then redirect to the presigned URL.
- Updated UI to show a paperclip action on expenses with receipts.
- Added env var: `S3_PRIVATE_MEDIA_EXPIRE_SECONDS`.

## 2026-02-13 — Phase 6D: Direct-to-S3 uploads + project file secure workflow

- Added Storage API endpoint: `POST /api/v1/storage/presign/` (Manager+) to generate **presigned POST** policies for private bucket uploads.
- Implemented **direct-to-S3 uploads** in UI for:
  - Expense receipts (expense form)
  - Project files (project files page)
  - Browser uploads to S3 first, then submits the object key to the app.
- Added env vars: `S3_DIRECT_UPLOADS`, `S3_PRESIGN_MAX_SIZE_MB`, `S3_PRESIGN_EXPIRE_SECONDS`.
- Updated docs: `docs/MEDIA_STORAGE.md` includes AWS CORS example for private bucket.

## 2026-02-14 — Phase 6F: Service Catalog integration + navbar live timer + pause/resume

- Project create/edit **Services** section is now table-based and looks intentional.
- Project services now use **CatalogItem (Service)** dropdowns (company-scoped, active only) with optional custom service names.
- Navbar timer now shows **project + live elapsed time** and provides **pause/resume** without opening the dropdown.
- Timer supports pause/resume using persisted `elapsed_seconds` + `is_paused`/`paused_at` fields.

## 2026-02-14 — Phase 6F.2: Render error-page hotfix (missing _public_shell.html)

- Added `templates/_public_shell.html` as a compatibility shim so `404.html` and `500.html` can render reliably.
- Prevents error-handler recursion on production if a server error occurs during public flows.

## Snapshot 2026-02-14 — Render Hotfixes (Migrations + Templates + Email Verify Resend)

### Fixed
- **Billing migration 0003** made idempotent for production DBs where the prior index name does not exist (guards rename/create).
- Restored compatibility template **`templates/_public_shell.html`** so error pages render in production.
- Updated **404/500** templates to link to the public home route (removed broken `dashboard:` namespace).
- Fixed **verify-email resend routing** by placing `verify-email/resend/` before `verify-email/<token>/` to prevent “resend” being treated as a token.
- Added `@login_required` + Ops alert on resend email failure (best-effort; never blocks user flow).


## 2026-02-14 — Phase 6H (Ops: PII Export + SLO webhook freshness)
- Added staff-only PII export: /ops/pii-export/ exports company data to CSV ZIP (clients/projects/documents/payments/expenses/time entries).
- Enhanced SLO dashboard with Stripe webhook freshness (last received/last ok + failures last 24h).

## 2026-02-14 — Phase 6I (Security: 2FA enforcement for Admin/Owner)
- Login now supports 2FA-enabled accounts: password auth creates a pending 2FA challenge and redirects to `/accounts/2fa/verify/`.
- Added session-scoped 2FA marker with TTL (`TWO_FACTOR_SESSION_TTL_SECONDS`, default 12h).
- Company-scoped pages enforce 2FA as a step-up gate:
  - Admin/Owner roles are always required to pass 2FA.
  - Company policy flags (`require_2fa_for_all`, `require_2fa_for_admins_managers`) and `employee.force_2fa` also trigger enforcement.
- Added `/accounts/2fa/confirm/` for already-authenticated step-up confirmation.

## 2026-02-15 — UI Shell Responsive + Theme Toggle
- Added first-class EZ360PM brand theme (blue/green) via CSS variables with light/dark modes.
- Implemented light/dark toggle in top navbar (persisted in localStorage; defaults to OS preference).
- Sidebar now scrolls when content exceeds viewport height (no disappearing links).
- On mobile, sidebar collapses into an off-canvas drawer with overlay + hamburger toggle.
- Topbar actions collapse into a mobile menu (three-dots button) to prevent overflow.
- Added Bootstrap JS bundle (CDN) and kept safe fallbacks where needed.
Files: templates/base_app.html, templates/base_public.html, static/ui/ez360pm.css, static/ui/ez360pm.js

## 2026-02-15 — Phase 6J (Render Staticfiles: WhiteNoise)
- Enabled WhiteNoise middleware + compressed manifest static storage so `/static/` serves correctly on Render when `DEBUG=False`.
- Added `whitenoise>=6.7.0` and documented the requirement that `collectstatic` must run during deploy.

## 2026-02-15 — Phase 6K1 (Mobile Topbar Fix + Sentry Init)
- Fixed iOS/mobile topbar overlap by enforcing responsive brand logo sizing (`.ez-brand-logo`) and consistent topbar sizing (`.ez-topbar`) with safe-area insets.
- Public + app shells now use the same topbar classes and brand logo styling.
- Enabled Sentry initialization when configured by calling `init_sentry_if_configured()` after `apply_runtime_defaults()`.

## 2026-02-15 — Phase 6K2 (Timer Dropdown Reliability + Invoice Lock UX)
- Timer navbar widget dropdown is now **JS-driven and Bootstrap-independent** (prevents “click does nothing” on mobile/prod).
  - Removed `data-bs-toggle="dropdown"` from the timer button.
  - Added explicit toggle logic that adds/removes `.show` and closes on outside click / Escape.
- Locked invoices now render in **read-only mode** on the edit screen:
  - All fields/line-items are disabled.
  - The Save button becomes a disabled “Locked” button.
  - Context now passes `is_locked` + `lock_reason` for consistent messaging.

### 2026-02-15 — Phase 6M1
- Ops Launch Checks expanded: verifies WhiteNoise static config + adds smoke checks for core data presence.
- Goal: reduce 'it works locally' drift by surfacing config and workflow readiness in a single screen.

### 2026-02-15 — Phase 6N (Ops Email Diagnostics)
- Added **Ops → Email test** (staff-only) to send a real test email and record results.
  - Stores an audit row per attempt (SENT / FAILED) including backend, from address, latency, and error text.
  - Failures create an Ops Alert (EMAIL / ERROR) for visibility.
- Launch Checks now include:
  - `DEFAULT_FROM_EMAIL` configured check.
  - “Recent successful email test (last 7 days)” evidence check (warns in prod until you run one).

### 2026-02-15 — Phase 6O (Error Page Hardening)
- Fixed `404.html` and `500.html` to avoid invalid URL namespaces and link to the stable `home` route.
- Added request correlation to error pages (shows Request ID when available).
- Hardened `core/error_views.py` so error templates never recurse (fallback to minimal HTML if template rendering fails).

### 2026-02-15 — Phase 6O2 (Clients Pagination Hotfix)
- Fixed a production 500 on `/clients/` caused by templates calling `page_obj.previous_page_number` / `next_page_number` when on the first/last page.
- Updated the clients list template to guard prev/next rendering via `has_previous/has_next`.

### 2026-02-15 — Phase 6P (Monitoring Gate: Ops Probes)
- Added **Ops → Probes** page with staff-only tools to validate monitoring in each environment.
  - **Test error**: intentionally raises a 500 and records an `OpsProbeEvent` (used to confirm Sentry captures exceptions).
  - **Create test alert**: creates an INFO Ops alert (source=PROBE) and records an `OpsProbeEvent`.
- Launch Checks now require evidence of a Sentry test error within the last 30 days when `SENTRY_DSN` is configured.


## 2026-02-15 — Pack: Optional 2FA enforcement + Client email index
- Changed 2FA enforcement: no longer forced by role; enforced only via Company/Employee admin flags.
- Company default 2FA enforcement now defaults to OFF unless env explicitly enables it.
- Added DB index for Client(company, email) + migration (crm 0002) to improve search/import performance.


## Hotfix (2026-02-15)

- Fixed getting-started crash by adding back-compat URL name `documents:numbering` (aliases to Document settings).

## 2026-02-15 — Phase 6O.3: UI reliability polish
- Hardened mobile navigation UX:
  - Sidebar now locks body scroll when open and auto-closes on link click (mobile/tablet).
  - Switching to desktop breakpoint closes any open drawers automatically.
- Sidebar Company switcher dropdown no longer depends on Bootstrap JS; uses deterministic dropdown toggle.


## 2026-02-15 — Phase 6O.4: Accessibility polish
- Added skip-to-content link and focus-visible styling.
- Improved keyboard behavior for custom dropdown toggles.

## 2026-02-15 — Phase 6R.1: Reconciliation affordance + perf micro-hardening
- Added a **Reconcile** button on the invoice edit screen (Manager+) linking to `payments:invoice_reconcile`.
- Reduced memory usage for staff-scoped Clients list by keeping `id__in` as a DB subquery (no Python `list()` materialization).


### Phase 6S (2026-02-15)
- Adjusted 2FA enforcement: no implicit role-based forcing; enforcement is only via Company policy flags (`require_2fa_for_all`, `require_2fa_for_admins_managers`) or `employee.force_2fa`.
- Added Projects DB indexes for common filters/sorts: (company, assigned_to), (company, client), (company, updated_at).

## 2026-02-15 — Phase 6T: Accounts Payable (MVP)
- Added new **payables** app with Vendor + Bills + Bill line items + Bill payments.
- Bills have a Draft → Posted lifecycle; posted bills are locked for edits.
- Posting a bill creates an accounting Journal Entry (`source_type='bill'`) that debits expense accounts and credits **Accounts Payable**.
- Recording a bill payment creates a Journal Entry (`source_type='bill_payment'`) that debits **Accounts Payable** and credits the selected cash/bank account.
- Added sidebar nav entries: **Bills (A/P)** and **Vendors** (manager+).


## 2026-02-15 — Phase 6T.1: Vendor unification + payables dashboard/ledger
- Unified vendor concept: deprecated **crm.Vendor** and migrated data into **payables.Vendor** (UUIDs preserved).
- Expenses now reference **payables.Vendor** so vendors are consistent across payables + expense tracking.
- Added Vendor detail (ledger-style) page: open balance, recent payments, and bill history.
- Added Dashboard Payables card: outstanding payables + due-soon count (7 days).
- Sync registry now includes back-compat mapping for `crm.Vendor` → `payables.Vendor`.

## Snapshot 2026-02-15 — Phase 7C (Payables: A/P Aging + Bill Attachments)

### Shipped
- Added **A/P Aging** report page + CSV export:
  - `GET /payables/reports/ap-aging/`
  - `GET /payables/reports/ap-aging.csv`
- Bills list supports **Due soon** filter (next 7 days).
- Vendor detail “New bill” button now preselects that vendor.
- Added **BillAttachment** model + admin support (stores private `file_s3_key`).
- Bill detail page supports **direct-to-S3 bill attachments** when `USE_S3=1` and `S3_DIRECT_UPLOADS=1`.
- Storage presign supports new kind `bill_attachment` using keys:
  - `private-media/bills/<company_id>/<bill_id>/<uuid>_<filename>`

### Notes
- This pack registers attachments after upload; secure download (presigned GET) is a follow-up pack.

## 2026-02-15 — Phase 7D (Payables): secure bill attachment downloads
- Added `core.s3_presign.presign_private_download()` for private-bucket presigned GET URLs.
- Added `payables:bill_attachment_download` route and UI Download button on Bill detail attachments table.
- Added `S3_PRESIGN_DOWNLOAD_EXPIRE_SECONDS` setting (default 120s).

## 2026-02-15 — Phase 7G.1 Hotfix: Services admin link
- Fixed a production 500 on **/projects/new/** caused by the admin reverse `admin:catalog_catalogitem_changelist` not resolving.
- Root cause: **CatalogItem** existed but was **not registered in Django Admin**, so the admin URL name was missing.
- Added `catalog/admin.py` registration for `CatalogItem` (list/search filters) so “Manage services” link works.

## 2026-02-15 — Phase 7G1 (Help Center wiring + manual skeleton kickoff)
**Done:**
- Added Help Center + Legal routing into `config/urls.py` by including `helpcenter.urls`.
- Updated top-nav Help button to route to `helpcenter:home`.
- Confirmed 2FA policy is **optional** and controlled via company/employee settings (no role-forcing).

**Found during static code check:**
- Help Center existed but was unreachable (not included in root URLs) — now fixed.
- Catalog/services exist (admin) but are not yet first-class UI for non-admin users.
- TimeEntry model still contains both `client` and `project` fields; UX should remain project-driven with client derived.

**Next focus:**
- Expand Feature Inventory into full User Manual (role-by-role, feature-by-feature).
- Add automated smoke/invariant checks beyond `ez360_smoke_test`.
- Corporate polish pass (forms, dollars formatting, email templates, UX consistency, ops readiness).

## 2026-02-15 — Phase 7G2 (Corporate polish: Catalog UI + project-driven time + money helpers)

**Shipped:**
- Added in-app **Catalog** UI (Manager+): list/search/filter + create/edit/delete.
- Added `core.templatetags.money.money_cents` to standardize `$xx.xx` formatting for cent-based amounts.
- Added `core.forms.money` helpers (parse dollars safely; cents conversion).
- Payments: Decimal-safe dollars→cents conversion and $ placeholders.
- Time tracking: enforce project-driven client alignment for `TimeEntry` and `TimerState` (auto-derive client; block mismatch).

**Notes / Follow-ups:**
- Still need to apply money formatting and $-input UX to invoices, expenses, bills, and accounting surfaces.
- Still need to enforce TimeEntry state locks after Approved/Billed.


## 2026-02-16 — Phase 7H (Pack 7H1) — Money UX completion for Expenses/Payables/Payments + smoke-test alignment

**Shipped**
- Standardized **money inputs** to cents-backed `MoneyCentsField` across:
  - Expenses (`ExpenseForm`: `amount_cents`, `tax_cents`)
  - Payables (`BillForm.tax_cents`, `BillLineItemForm.unit_price_cents`, `BillPaymentForm.amount_cents`, `RecurringBillPlanForm.amount_cents`)
  - Payments (`PaymentForm.amount_cents`)
- Updated templates to render dollar inputs consistently using Bootstrap **input-group** `$` prefix.
- Fixed a real template bug in `templates/expenses/expense_form.html` (`{% load static file_extras %}`).
- Updated `ez360_smoke_test` to match project-driven time-entry policy (no separate client selection).

**Why**
- Removes float rounding drift and eliminates mixed “dollars vs cents” UI.
- Moves EZ360PM closer to “corporate-grade” consistency and reduces user mistrust/friction.

**Next**
- Apply money UX standard to any remaining modules displaying raw cents (reports, admin list columns, dashboards).
- Expand smoke/invariant suite: document totals math, partial payments/credits, posting idempotency.


## 2026-02-16 — Phase 7H2
**Context:** Corporate hardening continued after Phase 7H1.

**Changes shipped:**
- Payments: implemented missing `PaymentRefundForm` used by `payments.views` (refund UI functional again).
- Added `manage.py ez360_invariants_check` to validate invoice/payment invariants (totals and paid/balance sanity).
- Documents: improved money-entry UX in line item editors (unit price + tax `$` input groups).
- Documents: removed raw cents debug display from Credit Note post confirmation.

**Notes / Next:**
- Extend invariants to cover credits/credit-notes and journal posting idempotency.
- Add “service on the fly” to the navbar timer dropdown.
- Standardize money rendering across dashboards/admin list columns (use `|money`).

## 2026-02-16 — Phase 7H3 (Invariants + Timer Service Creation + Admin Money Formatting)

**Shipped:**
- Timer: added **“Save as catalog service”** (Manager+) when starting the timer (navbar dropdown + timer page). If checked, typed service name is created as an active **CatalogItem (Service)** and linked to the timer.
- Invariants: expanded `manage.py ez360_invariants_check` to also scan **posted credit notes** (must have journal entry; applied cents in range) and **journal entries** (must be balanced).
- Admin money formatting: formatted money amounts in key Django Admin lists (Payments, Catalog items, Documents) using `format_money_cents`.

**Notes / Next:**
- Standardize remaining admin list displays (Expenses, Payables) and any lingering raw cents in templates.
- Expand invariants further: client credit ledger/application reconciliation; payment refunds vs invoice paid snapshots; posting idempotency audits.

## 2026-02-16 — Phase 7H5 — Invariants suite reliability + client credit sanity

**Code**
- Replaced the previous `ez360_invariants_check` implementation with a clean, sectioned version (Invoices / Payments+Refunds / Client Credits / Journals).
- Added client credit rollup sanity warnings (ledger sum vs `Client.credit_cents`) and credit application integrity checks.
- Added journal balance validation and stronger provenance checks.

**Docs**
- ROADMAP updated with Phase 7H4 and Phase 7H5 completion notes + next steps.
- DECISIONS updated to reflect invariants command scope and CI usage.

**Next**
- Add deeper credit availability checks (requires snapshot or replay approach).
- Add idempotency coverage audit for JournalEntry provenance across all posting sources.
- Add DB-backed “timer last used selections” persistence per employee.

## 2026-02-16 — Phase 7H6 Hotfix (Template Syntax)
- Fixed `templates/base_app.html` timer clear-selections condition (Django templates do not support parentheses in `{% if %}` expressions).



## 2026-02-16 — Phase 7H7 (Accounting Refund Posting Hardening)
- Fixed missing `Sum` import in `accounting/services.py` which broke refund journal posting.
- Hardened payment refund proration logic to use integer math (no float/round drift) when allocating refund between A/R and Customer Credits based on the original payment journal.
- Carried forward from Phase 7H6a hotfix (template-safe timer clear logic).

Next:
- Expand invariants to validate payment-refund journals are balanced and present for succeeded refunds.
- Consider adding a small unit test for refund proration edge cases (all AR vs all credits vs mixed).

## 2026-02-16 — Phase 7H9 — Readiness Check + Ops UI wiring
- Added `ez360_readiness_check` management command (non-destructive): validates env basics, DB connectivity, pending migrations, media storage writability, and email backend connectivity.
- Added Readiness Check option to Ops → Checks UI (staff-only) so launch evidence can be collected without CLI access.
- Updated Ops checks form/view/template wiring to include the new check.


## 2026-02-16 — Phase 7H10 — Email polish + contextual help links

- Fixed SUPPORT_EMAIL defaults in email templates and verification email.
- Email base template footer now references Support email and Help Center.
- Document emails now include support_email in context for consistent branding.
- Added contextual Help buttons to Dashboard, Time, Documents, Bills, and Payments pages.


## 2026-02-16 — Phase 7H11 (Ops Checks History + Options)
- Enhanced Ops Checks UI with Company picker + Quiet/Fail-fast options.
- Added OpsCheckRun model + admin for run history and launch evidence.
- Ops Checks page now shows recent run history with expandable output.

## 2026-02-16 — Phase 7H12 (DONE)
- Timer UX: added "Open selected project" shortcut links in navbar timer dropdown and timer page when a project is selected.
- Docs updated and roadmap advanced to next hardening items.

## 2026-02-16 — Phase 7H13 (Money display unification)
- Standardized currency formatting so all legacy `|cents_to_dollars` outputs now match the corporate standard `$x,xxx.xx`.
- Updated key UI surfaces to prefer `|money` over `|money_cents` (dashboard + catalog list).
- No behavior changes to underlying cents storage; this is display-only polish.


## 2026-02-16 — Phase 7H14 (Email subject standard + Ops evidence export)
- Email subjects are now normalized via `core.email_utils.format_email_subject()` (trim, prefix, optional separator, 200-char cap).
- Ops/alert emails (`core.ops_alerts.alert_admins`) and `ez360_ops_report` now use the subject normalizer to enforce consistent branding.
- Ops Checks output now has a truncation guardrail that appends an explicit "[output truncated]" marker.
- Added staff-only download endpoint for OpsCheckRun output (Ops → Checks → Recent Runs → download).

Next:
- Expand Help Center content with deeper page-by-page walkthroughs and screenshots.
- Add OpsCheckRun CSV export for audit/compliance evidence if needed.

## 2026-02-16 — Phase 7H15 (Ops seat limit fix)
- Fixed Ops dashboard crash by removing direct `subscription.seats_limit` access; seat limits are computed via `billing.services.seats_limit_for(subscription)`.
- Documented the computed-seat policy to prevent regression.

## 2026-02-16 — Phase 7H16 (Recurring bills template + help wiring)
- Fixed TemplateSyntaxError on recurring bills list by loading the `money` template filter library.
- Added a contextual Help button on Recurring Bills list pointing to Help Center → Accounting.

## 2026-02-16 — Phase 7H17 (Ops company UUID routes)
- Fixed Ops dashboard NoReverseMatch caused by UUID company IDs not matching `<int:company_id>` URL patterns.
- Ops company detail/timeline/resync URLs now use `<uuid:company_id>`.


## 2026-02-16 — Phase 7H18 (Template sanity + UUID company checks)
- Added `ez360_template_sanity_check` and wired it into Ops → Checks.
- Fixed Ops checks to treat Company IDs as UUID strings (no int casts).
- Updated smoke/idempotency commands to accept UUID company IDs.
- Added form validation: smoke test requires selecting a company.

## 2026-02-16 — Phase 7H19 (Ops checks indentation + template sanity hardening)
- Fixed an IndentationError in ops/views.py that prevented Django from loading config/urls.py.
- Hardened ez360_template_sanity_check to flag missing `{% load money %}` when templates use `|money` or `|money_cents`.

## 2026-02-16 — Phase 7H21 (URL sanity + Ops wiring)

- Added `ez360_url_sanity_check` command and wired it into Ops → Checks.
- Added Ops check kind `URL_SANITY`.
- Fixed OpsChecksForm indentation regression; added UUID-safe drift forms.

## 2026-02-16 — Phase 7H22 (Ops Run-All + Help Center expansion)
- Ops Checks: added **Run all** convenience option (runs everything; skips Smoke Test when no company selected).
- App shell: added **Help Center** link to the left sidebar.
- Help Center: expanded home page topic tiles to cover core workflows (Time, Invoices & Payments, Accounting, Billing, FAQ, Legal).

## 2026-02-16 — Phase 7H23 (Help Center fill + Template sanity expansion + Ops evidence export)
- Template sanity expanded: warns on POST forms missing `{% csrf_token %}` and warns on `{% url %}` tags using un-namespaced view names (heuristic).
- Help Center: added new pages for Recurring Bills, Refunds, and Ops Console; wired new tiles on Help Center home.
- Ops Checks: added one-click export of recent runs as a ZIP bundle (includes runs.csv + per-run output files).



## 2026-02-16 — Phase 7H24 (DONE)
- Expanded `ez360_url_sanity_check` to warn on obvious `{% url %}` positional arg-count mismatches for the top 20 most-used routes (best-effort).
- Added contextual help deep links:
  - Recurring Bills list → Help Center → Recurring Bills.
  - Payment/Refund screen → Help Center → Refunds.
  - Bill detail → Help Center → Accounting.
- Added scheduled/retention commands for Ops evidence:
  - `ez360_run_ops_checks_daily` (persist OpsCheckRun runs; intended for daily scheduler)
  - `ez360_prune_ops_check_runs` (retention by days, protects recent-per-kind)
- Help Center Ops Console updated with daily routine guidance.
