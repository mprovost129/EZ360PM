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
  - Env: `OPS_ALERT_WEBHOOK_TIMEOUT_SECONDS`

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
