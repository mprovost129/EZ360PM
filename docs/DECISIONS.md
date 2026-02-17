## UI / Launch Prep

### Dashboard KPI definitions (Phase 8B)
- Revenue: sum of succeeded payments in the current month net of refunded cents.
- Expenses: sum of approved/reimbursed expenses in the current month.
- A/R: sum of invoice balance due for sent + partially paid invoices.
- Unbilled time: approved billable time with no billed document (minutes → hours).

## 2026-02-16 — Phase 7H46
- **Help Center screenshot key governance:** required screenshot keys are tracked explicitly in `helpcenter/required_screenshots.py` and reviewed via an admin checklist view (`/admin/helpcenter/helpcenterscreenshot/required-keys/`).
- **Ops snooze operability:** ops dashboards must show snooze end timestamps and allow a one-click clear to reduce “why is this hidden?” operator friction.
- **Collections notes scope:** collections notes are stored per-client (company-scoped), support an optional follow-up date, and are completed via status (no hard delete).

## 2026-02-16 — Phase 7H45
- Help Center screenshots: implemented as DB uploads (admin-managed) with a stable `key` and template fallback to static placeholders to avoid code changes for screenshot swaps.
- Ops snooze UX: standard quick-pick durations (30m/2h/1d/7d) and “Snoozed” badge derived from active snooze records, scoped by (source, company or platform).

## 2026-02-16 — Phase 7H29

- **Daily ops checks alerting:** scheduled checks MAY emit OpsAlertEvent + webhook + mail_admins when failures occur; alerts must never break the request path.
- **Financial statements help:** P&L / Balance Sheet / Trial Balance pages are documented in Help Center and linked contextually from reports.

## 2026-02-16 — Phase 7H42

- **Statement email tones:** Statements support three tone variants — `sent` (standard), `friendly`, and `past_due`. UI preview must reflect the selected tone before sending.
- **Collections reminders workflow:** Statement reminders are manageable from a company-wide queue with bulk cancel/reschedule (cap 500 per action) to support collections operations.
- **Ops alert exports:** Ops supports one-click CSV export of unresolved alerts (filters respected; capped) for vendor/support escalations.

## Template sanity policy (money/static tag libraries)

- Any template that uses `|money` or `|money_cents` MUST include `{% load money %}`.
- Any template that uses `{% static %}` MUST include `{% load static %}`.
- Parentheses inside `{% if %}` are treated as a warning because Django templates frequently break on them; prefer nested `{% if %}` blocks.

## 2026-02-16 — Decision: Seat limits are computed, not stored
- `CompanySubscription` does not store `seats_limit`.
- Any UI/ops surfaces must compute seat limits using `billing.services.seats_limit_for()` (included seats by plan + extra_seats).
- Avoid accessing `subscription.seats_limit` directly.

## 2026-02-16 — Timer persistence policy
- The timer keeps the last selected **project/service/note** when stopped.
- Clearing selections is an explicit user action via **Timer Clear** (not automatic).
- This improves repeat workflow speed and reduces friction for staff users.

## 2026-02-16 — Ops checks must be runnable from UI (staff-only)
- Corporate ops requires that evidence-producing checks are runnable from the Ops Console.
- `/ops/checks/` is staff-only and runs a constrained set of safe management commands, capturing stdout.
- Supported checks (v1): smoke test, invariants, idempotency scan.

## 2026-02-16 — Timer defaults are persisted in TimeTrackingSettings
- TimerState is ephemeral (can be recreated). Therefore, last selections are persisted in `TimeTrackingSettings`:
  - `last_project`, `last_service_catalog_item`, `last_service_name`, `last_note`
- When TimerState is created/recreated and has no selections, it rehydrates from these fields.

## 2026-02-16 — Phase 7H4 Decisions
- **Admin money formatting:** Admin list/inline displays must show dollars (`$xx.xx`) via `format_money_cents()`; avoid raw cents in operator UI.
- **Refund invariants:** Refund totals must never exceed payment amount; `refunded_cents` must be non-negative and <= amount; mismatches vs refund rows are warnings until legacy cleanup is complete.
- **Timer catalog UX:** Provide a direct management link for catalog services from timer UI for Manager+ roles.

## 2026-02-16 — Money UX standard (dollars UI, cents storage)

- All money amounts are stored as **integer cents** (BigInteger) for consistency and safe arithmetic.
- All user-facing money inputs must accept/emit **dollars** (`$xx.xx`) using `core.forms.money.MoneyCentsField`.
- Templates should use `{% load money %}` and the `|money` filter (alias of `|money_cents`) to display cents as dollars.

## 2026-02-15 — Private media deletion behavior
- Private media (S3) deletions are **best-effort** and **configurable** via `S3_DELETE_ON_REMOVE`.
- Records remain soft-deleted for audit/history even when the underlying object is removed.

## 2026-02-15 — Unified private media access + preview

- All private media access (receipts, project files, bill attachments) routes through a shared helper that:
  - Generates **attachment** links by default.
  - Generates **inline preview** links only for PDFs/images (via `?preview=1`).
- Templates must not expose raw bucket URLs; they link to app routes which then redirect to presigned URLs.
- When using S3, presigned preview uses `ResponseContentDisposition=inline`; downloads use `attachment`.





# EZ360PM — Locked Decisions (Post Phase 3A)

## 2026-02-13 — Phase 6D: Direct-to-S3 uploads for private media

- For large/private uploads (receipts, project files), the browser uploads directly to the **private S3 bucket** using a **presigned POST** generated server-side.
- The app stores the resulting object key in the FileField (via hidden key fields) to avoid large request bodies through the web app.
- Access remains permission-gated in-app; downloads use presigned URLs from `PrivateMediaStorage`.

## 2026-02-14 — Phase 6E: Currency inputs + timer UX

- **All user-facing currency inputs** are entered as dollars (`$xx.xx`) and converted to integer cents internally.
- **Timer UX** is global and lightweight: timer controls live in the navbar (dropdown), and stopping the timer creates a **draft** time entry.
- Timer metadata is minimal: project + optional single service + notes; client is derived from the project relationship.


## 2026-02-13 — Phase 5A: Getting Started UX + Computed Checklist

- The onboarding checklist is **computed** from live data (no manual checkboxes) so it remains correct even if users import clients/projects/documents.
- The app shell (sidebar) needs onboarding visibility, but must remain cheap:
  - We compute a lightweight `onboarding_progress_nav` using `.exists()` checks rather than `.count()` to reduce load.
  - Any failure to compute onboarding progress must not break page render (best-effort only).

## 2026-02-13 — Security defaults are production-on (Phase 3R)

- Email verification gate defaults **ON** when `DEBUG=False` (override via `ACCOUNTS_REQUIRE_EMAIL_VERIFICATION`).
- Company onboarding defaults to require **2FA for managers/admins/owners** in production (override via `COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS`).
- `SECURE_SSL_REDIRECT`, secure cookies, and HSTS default ON in production.

## 2026-02-13 — CSP rollout is report-only by default (Phase 3U)

- CSP is enabled by default in production (`EZ360_CSP_ENABLED=1`) but ships in **report-only** mode (`EZ360_CSP_REPORT_ONLY=1`) until validated.
- Enforcing CSP is an explicit opt-in (`EZ360_CSP_REPORT_ONLY=0`).
- CSP allowlist must reflect runtime template assets (currently allows jsDelivr CDN for Bootstrap + Icons).

## 2026-02-13 — Ops alerting is best-effort (Phase 3T)

- Immediate ops alerts for Stripe webhook processing failures and email delivery failures are **best-effort** and must never break the request path.
- Enabled by default in production and controlled by:
  - `EZ360_ALERT_ON_WEBHOOK_FAILURE`
  - `EZ360_ALERT_ON_EMAIL_FAILURE`

## 2026-02-15 — Topbar logo sizing is constrained

- The EZ360PM brand mark must never exceed the topbar height (prevents iOS overlap/covering issues).
- Use `.ez-topbar` + `.ez-brand-logo` classes for both public + app shells; logo height is responsive (smaller on phones).

## 2026-02-15 — Sentry is opt-in via env

- Sentry is initialized only when `SENTRY_DSN` is set.
- Initialization happens after runtime defaults are applied so the environment/release metadata is correct.

## 2026-02-14 — Presence + SLO dashboards are lightweight and non-invasive (Phase 6G)

- Presence tracking exists only to support staff SLO visibility (active users in the last N minutes).
- Presence writes are **throttled** (at most ~1 DB write per minute per session) and must never affect request handling.
- Presence is tracked at `(user, company)` granularity using `ops.UserPresence.last_seen`.
- Optional external ops alert webhook delivery (`OPS_ALERT_WEBHOOK_URL`) is **best-effort** and must never block requests or create recursive alert loops.

## 2026-02-14 — Migration safety: index renames must be idempotent (Render hotfix)

- Any migration that renames DB indexes must **not assume** the old index name exists in every environment.
- If a `RenameIndex` can fail (common after branch drift, older Django versions, or manual DB changes), implement the DB step as guarded SQL using `to_regclass(...)` checks via `SeparateDatabaseAndState`.
- Prefer **rename-if-exists + create-if-missing** to keep production deploys unblocked.


## 2026-02-13 — Client Credit Ledger & Applications (Phase 3J)

- **Source of truth:** `ClientCreditLedgerEntry` is authoritative for client credit balance.
- `Client.credit_cents` is a **cached rollup** synced from the ledger (never treated as source of truth).
- Applying client credit to an invoice creates an immutable application record and posts accounting:
  - **DR** Customer Credits (liability)
  - **CR** Accounts Receivable
- Invoice stored `balance_due_cents` is recomputed from:
  - payments + posted credit notes + credit applications.

## Financial Rules

1. Invoice Financial Immutability
   - Draft: editable
   - Sent: monetary fields locked
   - Partially Paid: monetary fields locked
   - Paid: fully immutable

2. Journal Entries
   - Once posted, never mutated
   - No line replacement allowed

3. Status Transitions
   - No downgrade allowed from SENT or above
   - Paid cannot change status

## Architectural Direction

- Credit notes will be implemented as separate model (future phase)
- Reversals will be additive, never mutative
- Reconciliation will be read-only diagnostic layer

## Operational Direction

- No major financial refactors without incremental validation
- ZIP snapshots represent stable checkpoints



## Credit Notes
- Credit notes require invoice SENT+ (no credit notes for DRAFT/VOID).
- Credit note numbers are per-company sequence: CN-YYYYMM-####.


## Credit Note Editing
- Draft credit notes are editable.
- Posted credit notes are immutable (except via reversal in future phase).
- UI uses dollars; database stores cents.

## Backups & Recovery
- Backups are performed using `pg_dump` custom-format dumps for PostgreSQL (`.dump`) and are pruned via retention rules.
- Restores are manual/explicit using `pg_restore` to reduce accidental destructive operations.
- Media backup tarballs are optional and intended for single-server deployments; object storage is preferred for production.

## Soft-delete Guardrail
- Models inheriting `core.models.SyncModel` default to soft-delete (tombstone via `deleted_at`) when `.delete()` is called; hard deletes require `hard=True`.


## Monitoring & Observability
- Health checks must validate DB connectivity (not just return static OK).
- Request ids are required for production troubleshooting; the app honors inbound X-Request-ID and always returns it.
- Sentry is optional but first-class; the app must boot even if sentry-sdk is not installed.
- Slow requests are logged above a configurable threshold (EZ360_SLOW_REQUEST_MS).

## UX & Premium Experience
- Onboarding checklist is **computed** from live data (not stored) so it stays accurate after imports and bulk actions.
- Global alerts are dismissible and map Django's `error` level to Bootstrap `danger`.

## Subscription Tiers & Feature Gating (Phase 3J+)

- Plan tiers are **Starter → Professional → Premium**.
- Accounting is included in **Professional+**.
- Extra seats are billed as a separate Stripe subscription item with **quantity = extra seats**.
- Seat limit is computed as: **included seats(plan) + extra seats** (never by hard-coded “seat tiers”).
- Feature gating is enforced in code via:
  - `tier_required(min_plan)` for coarse plan checks
  - `plan_allows_feature(feature_code)` for named features

## Ops access model
- Keep Django superuser for break-glass only (rare use).
- Day-to-day operations should use staff users (is_staff) + Ops Console + Support Mode.
- Support Mode is the sanctioned way to access/inspect tenant data; all support actions should be audit-logged.


## Stripe Subscription Resync (Staff-only)
- Staff can initiate a subscription refresh from Stripe API for a specific company.
- This is intended for support/diagnostics (webhook delays, customer portal issues).
- Result is written into CompanySubscription via the same sync pipeline used by webhooks.


## Refunds (v1)
- Refunds are modeled explicitly as PaymentRefund records and never mutate historical payments beyond refunded_cents rollup.
- Invoice balance due uses net payments (amount - refunded).
- Accounting uses a separate journal source_type 'payment_refund' to keep reversals auditable and idempotent.


## Advanced Reporting (Phase 3O)
- CSV exports are supported via query param `?format=csv` for core accounting reports.
- Project Profitability is treated as a Premium feature; reporting is journal-based (not derived from invoice/payment tables directly).

## Launch Readiness Checks (Phase 3P)
- We expose a lightweight, settings/env-based launch checklist in the staff Ops Console and via `python manage.py ez360_check`.
- Checks are intentionally non-blocking at runtime (they report risk, they don’t prevent server startup).

## Email configuration validation (Phase 6N)
- Production email configuration must be verifiable **from inside the app** (no shell required).
- Ops Console includes a staff-only “Email test” page that sends a real test message and records results.
- Launch Checks include an “email evidence” signal (recent successful test) to prevent silent misconfiguration.

## Ops Retention & Pruning (Phase 3Q)
- Retention policy is **env-driven** (no DB settings) to allow ops changes without migrations.
- Pruning uses **bulk deletes** (permanent removal) and is staff-only via Ops UI and a management command.
- We prune only operational data (audit events, Stripe webhook payloads); financial records are never pruned automatically.

## 2026-02-13 — Financial integrity hardening

- **Journal entries are immutable once posted.** If a correction is needed, we will create a correcting entry rather than mutating history.
- **Reconciliation is an explicit workflow.** Invoice balances must be explainable from: payments (net of refunds), posted credit notes, and applied client credits.

## 2026-02-13 — Performance indexing

- We add targeted composite indexes for the most common filters (company + status/date, company + invoice/client) rather than broad/duplicate indexing.
- `ClientCreditApplication` must declare indexes in `Meta.indexes` (class attribute `indexes = [...]` is ignored by Django); we fixed this to ensure indexes are actually created.

## 2026-02-13 — Phase 3W perf tooling and soft-delete indexing

- For soft-deleted models with heavy list views, prefer **partial indexes** with `condition=Q(deleted_at__isnull=True)` so Postgres can ignore deleted rows.
- Lightweight perf logging is done via a **dev-only middleware** (no extra dependencies) with env-driven thresholds.
- Perf checks are intentionally implemented as a management command that exercises the exact list querysets, providing a repeatable baseline without needing browser-driven profiling.

## 2026-02-13 — Phase 3X settings profiles

- Settings follow standard Django module layering:
  - `config.settings.base` contains shared defaults only.
  - `config.settings.dev` and `config.settings.prod` apply environment-specific overrides.
- Any defaults that depend on `DEBUG` (e.g., email verification on/off, secure cookie defaults, CSP rollout defaults) are centralized in `apply_runtime_defaults()` and re-run after `DEBUG` is set in the environment-specific modules.

## 2026-02-13 — Phase 3Y dev HTTP/HTTPS behavior

- Development must be reachable over plain HTTP by default; `SECURE_SSL_REDIRECT` and related production env values must not break local work.
- Local HTTPS testing is opt-in via `DEV_SECURE_SSL_REDIRECT=1` and requires running an HTTPS-capable local server.

## 2026-02-13 — Phase 4A: Observability defaults

- Health checks: Provide a lightweight `/healthz/` endpoint for uptime monitors and load balancers. It must not leak secrets and should return 500 on failed DB checks.
- Sentry: Initialize Sentry only when `SENTRY_DSN` is present. Initialization must be safe if `sentry-sdk` is not installed (app should still boot).
- Settings layering: Sentry init belongs in base as a helper and is invoked by environment-specific settings (dev/prod), not duplicated inline.

## 2026-02-13 — Phase 4B: DB-backed ops alerts

- Actionable failures and key degradations are persisted in-app via `ops.OpsAlertEvent` so staff can review and acknowledge them without server log access.
- Alert creation is **best-effort** (never raises) and must not block the request path.
- We store only minimal structured context needed to triage (no secrets; no full request bodies).
- Perf sampling is opt-in via env (`EZ360_PERF_*`) and stores only request-level timing and counts (no SQL persisted).


## 2026-02-13 — Phase 5B: Company financial defaults & provisioning
- Company stores default invoice due days and estimate/proposal valid days; used only for new document creation.
- Company stores sales tax percent as guidance only; tax remains explicitly entered on line items to avoid silent money changes.
- Onboarding provisions: numbering scheme, minimal chart of accounts, and a Default template per document type (idempotent).
- Empty states are treated as a first-class UX surface with direct actions.


## 2026-02-13 — Phase 6A: Launch readiness is both automated + human-gated
- Automated checks live in `core.launch_checks` and are exposed in Ops → Launch checks.
- The Launch Gate checklist is a staff-managed DB artifact (OpsLaunchGateItem) for items that require manual verification (prod 2FA, backup restore test, alert routing, end-to-end flows).
- Ops security visibility (lockouts + throttle/auth alerts) is staff-only and stores minimal context (no secrets).


## Phase 6B — Locked invoices are immutable (2026-02-13)

Decision:
- Once an invoice is **Sent** or any money-affecting event occurs (payment applied, client credit applied, posted credit note), the invoice is treated as **locked**.
- Locked invoices:
  - Cannot change money fields, client/project, or key dates.
  - Cannot have line items created/updated/deleted (including soft-delete).
- Rationale:
  - Prevents “retroactive AR edits” that break reconciliation and audit trails.
  - Keeps journal entries and stored invoice rollups stable after posting/payment.

## Phase 6C — Backups are host-managed; EZ360PM records evidence
- EZ360PM does not execute backups in-app in v1; backups are performed by the hosting platform (managed Postgres or scheduled jobs).
- We provide an Ops UI + models to record backup run outcomes and restore tests to satisfy Launch Readiness Gate.
- Dev defaults to BACKUP_ENABLED=0 to avoid surprising behavior.


## 2026-02-13 — Phase 7B release notes + preflight migration guard
- Release notes are manual staff entries (not generated from git) to keep the system simple and accurate.
- Preflight treats pending migrations as a release-blocker by default (can be disabled in CI via env if needed).


## 2026-02-13 — Phase 7C: Correlated logging + security posture checks
- Logging format includes `[rid=<request_id>]` for cross-request correlation (RequestIDMiddleware + contextvar filter).
- Launch checks include secure cookies + HSTS as warn-level guards; enforced only as recommendations in prod to avoid blocking early staging.


## 2026-02-13 — Backup execution lives in a management command

- Backups are run via `ez360_backup_db` so scheduling remains host/CI responsibility (cron/Render job/etc.).
- The app records immutable evidence (`BackupRun`) of runs and failures without blocking request paths.
- `pg_dump` is treated as an external dependency; if not on PATH, set `EZ360_PG_DUMP_PATH`.

## Backup retention is enforced by simple filesystem pruning
- Backups are host-managed files; the app provides **pruning** via a management command.
- We enforce retention via `BACKUP_RETENTION_DAYS` and optional `BACKUP_MAX_FILES` to avoid unbounded disk growth.
- Backup contents are never parsed by the app; only filenames and mtimes are used.

## 2026-02-15 — Optional S3 backup target
- If host-level DB snapshots are insufficient, EZ360PM can upload `pg_dump` outputs to S3.
- Controlled by env:
  - `BACKUP_STORAGE=s3`
  - `BACKUP_S3_BUCKET`, `BACKUP_S3_PREFIX`
- Upload metadata (bucket/key/sha256) is stored on the `BackupRun` row for auditability.
- Pruning supports both local filesystem and S3 object deletion using the same retention rules.


## 2026-02-13 — Phase 6F: Backup/restore evidence is host-scheduled + app-recorded
- EZ360PM provides backup and retention commands (`ez360_backup_db`, `ez360_prune_backups`) but does not run them automatically.
- Host scheduler (cron/Task Scheduler/Render cron job) is the source of truth for timing.
- The app records evidence of restore tests (Ops UI or `ez360_record_restore_test`) and raises Ops alerts on failed restore tests.


## 2026-02-13 — Soft-delete default manager + admin visibility

Decision:
- `SyncModel.objects` hides soft-deleted rows by default to prevent accidental reads/updates of tombstoned data.
- `SyncModel.all_objects` remains available for admin/maintenance tasks and for sync endpoints that must include tombstones.
- Django Admin changelists should include deleted rows where it is operationally useful (financial + CRM objects), implemented via `IncludeSoftDeletedAdminMixin`.

Rationale:
- Prevents “ghost” records from reappearing in UI.
- Avoids accidental mutation of deleted data.
- Keeps sync-safe tombstones without sacrificing admin auditability.

## 2026-02-13 — Media storage via STORAGES with optional S3

Decision:
- Default media storage is local filesystem for dev/simple deployments.
- Production can optionally use S3/S3-compatible storage controlled by `USE_S3=1`.
- If S3 is enabled, `django-storages[boto3]` is required (explicit dependency).



## 2026-02-13 — Phase 6C: Drift remediation + multi-bucket storage
- Drift fixes are staff-only, idempotent actions exposed in Ops to avoid direct DB surgery.
- Separate S3 buckets for public vs private media; private bucket used for receipts and project files by default.


## 2026-02-13 — Phase 6C.1: Private downloads use presigned S3 URLs, gated by app routes
Decision:
- Private files (receipts, project files) are never linked directly; access is routed through the app and then redirected to a **presigned URL**.
- Presigned URL lifetime is configurable via `S3_PRIVATE_MEDIA_EXPIRE_SECONDS` (default 10 minutes).

Rationale:
- Enforces company/role/project permissions before issuing a download.
- Keeps the S3 bucket private while still allowing safe browser downloads.

## Direct-to-S3 uploads for private media (Phase 6D)

Decision:
- When `USE_S3=1` and `S3_DIRECT_UPLOADS=1`, uploads for **private media** (receipts, project files) are performed **browser → S3** using a presigned POST policy.

Rationale:
- Avoids large multipart uploads through the Django server (better performance + fewer timeouts).
- Keeps private objects private: app controls who can generate presigns and who can download via signed URLs.

## 2026-02-14 — Services catalog is the source of truth

Decision:
- Company services are maintained in the **Catalog** as `CatalogItem(item_type=service)`.
- Project services should reference a catalog item when possible, but retain a stable `name` value for exports and historical correctness.
- Timer service capture uses either a catalog item or a custom name and is written onto the generated draft time entry.

Rationale:
- Keeps service lists consistent across projects/time entries.
- Allows admin-managed service vocabulary without forcing hard coupling.

## 2026-02-14 — Keep `_public_shell.html` as a compatibility shim

Decision:
- Maintain `templates/_public_shell.html` as a thin wrapper around `base_public.html`, mapping legacy `{% block public_content %}` to `{% block content %}`.

Rationale:
- Several public/error templates (404/500) extend `_public_shell.html`.
- Missing base templates can cause error-handler recursion in production; the shim makes error pages resilient.

## 2026-02-14 — Migration Safety + URL Routing Guardrails

- **Migration safety:** Any migration that renames DB objects (indexes/constraints) must be **idempotent** in production by checking existence before renaming/creating, because real prod schemas can diverge from local history.
- **URL routing:** Reserve literal routes (e.g., `verify-email/resend/`) **before** parameterized routes (e.g., `verify-email/<token>/`) to avoid accidental matches.
- **Error pages:** Error templates must not reference optional namespaces. Prefer stable root routes like `home`.


## Ops PII Export scope
- PII export is a portability/DSAR convenience tool that exports company-scoped business records as CSV inside a ZIP.
- It is not a full backup system and does not include private file blobs (S3 objects); backups remain the authoritative archival mechanism.

## 2026-02-14 — 2FA enforcement model (Admin/Owner mandatory)

Decision:
- 2FA is **mandatory** for company **Admin** and **Owner** roles.
- Enforcement is implemented as a **step-up** gate on company-scoped pages:
  - If the user has not confirmed 2FA in the current session, they are redirected to confirm.
  - If 2FA is not enabled, they are redirected to set it up.
- Login flow supports 2FA-enabled accounts by requiring a TOTP code before completing sign-in.

Rationale:
- Keeps security high for privileged roles while remaining lightweight (no third-party deps).
- Step-up flow avoids breaking the public/auth pages while still enforcing policy before sensitive access.

## 2026-02-15 — Shell theming + responsive behavior
- Theme is controlled client-side with `html[data-theme]` and persisted in `localStorage` key `ez360pm.theme`.
- Brand palette is expressed as CSS variables (no SCSS build step required).
- Mobile navigation uses a lightweight JS toggle + overlay (works even if Bootstrap JS fails).

## 2026-02-15 — Serve static files with WhiteNoise in production

Decision:
- Use **WhiteNoise** to serve `/static/` (including Django Admin assets) in production environments like Render.

Rationale:
- Removes dependency on platform-specific static route configuration.
- Ensures admin/app CSS works consistently with `DEBUG=False`.
- Provides hashed + compressed static assets via `CompressedManifestStaticFilesStorage`.

## 2026-02-15 — UI Reliability: timer dropdown is Bootstrap-independent

Decision:
- The **timer navbar dropdown** uses explicit, local JS toggling rather than Bootstrap’s dropdown plugin.

Rationale:
- The topbar has custom mobile/overlay behaviors and we’ve observed “click does nothing” cases on mobile/prod.
- A small deterministic toggle avoids CDN/JS availability issues and eliminates event-order conflicts.

## 2026-02-15 — Financial integrity UX: locked invoices render read-only

Decision:
- If an invoice is “locked” (sent/paid/credits applied), the edit UI renders in **read-only mode** (disabled fields + no Save).

Rationale:
- Prevents user confusion and reduces the chance of attempted mutations.
- Server-side lock already blocks POST edits; UI lock aligns the UX with invariants.

## 2026-02-15 — Error pages must never raise

Decision:
- `404`/`500` templates must avoid unstable URL namespaces and link only to stable routes.
- Error handlers must be defensive: if an error template fails, return minimal HTML to prevent recursive 500s.

Rationale:
- Production errors often occur during partial deploy/config drift; the error page must remain renderable.
- Prevents “error handler crashed” incidents that hide the real underlying exception.

## 2026-02-15 — Pagination templates must not call page-number methods unless available

Decision:
- Shared pagination templates must only call `previous_page_number()` when `page_obj.has_previous` is true, and only call `next_page_number()` when `page_obj.has_next` is true.

Rationale:
- Django raises `EmptyPage` if those methods are called at the bounds (page 1 / last page).
- “Disabled” pagination UI still evaluates template expressions; guarding prevents template-time exceptions.

## 2026-02-15 — Monitoring evidence as a launch gate when Sentry is enabled

Decision:
- If `SENTRY_DSN` is configured in production, EZ360PM requires a **recent Ops probe** (“Test error”) within the last 30 days.

Rationale:
- Configuration alone is not enough; we need positive evidence the monitoring pipeline works end-to-end.
- The Ops Probes screen provides a safe, staff-only workflow and records the evidence in-app.

### 2026-02-15 — Launch Check Philosophy
- Launch checks must be safe to run in dev/staging/prod without elevated DB privileges.
- Prefer settings/env validation + minimal existence queries over deep reconciliation (use Ops reconciliation/drift tools for that).


## 2026-02-15 — Pack: Optional 2FA enforcement + Client email index
- 2FA policy is opt-in by default; enforcement is controlled by admin-configurable Company flags and per-employee override.
- Avoid role-based mandatory security in v1 to reduce friction; enable enforcement in production via Company settings.


## Hotfix (2026-02-15)

- Prefer URL-name back-compat aliases over template churn when a broken link is already deployed in production.

## 2026-02-15 — Decision: Dropdown behavior must not depend on Bootstrap JS
To avoid production/mobile issues where dropdowns fail to open due to event ordering or JS loading, key navigation dropdowns (timer, company switcher) use deterministic toggles rather than Bootstrap's dropdown plugin.


## 2026-02-15 — Phase 6O.4: Accessibility polish
- Added skip-to-content link and focus-visible styling.
- Improved keyboard behavior for custom dropdown toggles.

## 2026-02-15 — Reconciliation must be reachable from invoice detail/edit screens

Decision:
- Manager+ users must be able to reach invoice reconciliation tooling directly from the invoice screen via an explicit **Reconcile** CTA.

Rationale:
- Reconciliation is an operational workflow; hiding it in Reports/Ops creates dead ends during QA and production support.

## 2026-02-15 — Prefer DB subqueries over Python materialization for staff scoping

Decision:
- When scoping list views by related objects (e.g., staff-visible clients via assigned projects), use DB-native `IN (subquery)` instead of converting IDs to Python lists.

Rationale:
- Reduces memory use and avoids request-time spikes on large datasets.


## 2FA enforcement policy (Phase 6S)
- 2FA is **optional by default**.
- The app does **not** force 2FA based on role alone.
- Enforcement is controlled by admin-configurable flags on Company and Employee: `require_2fa_for_admins_managers`, `require_2fa_for_all`, and `employee.force_2fa`.

## Accounts Payable (Phase 6T)
- A/P is implemented as a dedicated **payables** module (Vendor, Bill, BillLineItem, BillPayment).
- Posting creates immutable accounting artifacts:
  - `JournalEntry.source_type='bill'` for bill posting
  - `JournalEntry.source_type='bill_payment'` for bill payment
- Posted bills are treated as **locked** (cannot edit header or lines); only payments can be added.
- Overpayments are blocked at the service layer (payment amount cannot exceed current bill balance).


## 2026-02-15 — Vendor model consolidation
- There is a single Vendor model going forward: **payables.Vendor**.
- `crm.Vendor` was removed to avoid duplicated concepts and reverse-relations collisions.
- Vendor UUIDs are preserved during migration so existing FK values (e.g., expenses) remain valid after repointing.

## 2026-02-15 — Payables attachments stored as private S3 keys
- Bill attachments are stored as **private object keys** (`file_s3_key`) rather than public URLs or FileFields.
- Uploads use the existing **presigned POST** mechanism; downloads will use presigned GET later.
- Key convention: `private-media/bills/<company_id>/<bill_id>/<uuid>_<filename>`.

## Payables
- Vendors/Bills live in `payables` (A/P) and are company-scoped; posted bills are immutable.
- Bill attachments are stored in the private S3 bucket and accessed via short-lived presigned GET URLs (no public bucket exposure).
- Attachment removal is a soft-delete in the DB; S3 object deletion is optional and not required for correctness.


## 2026-02-15 — Recurring Bills (A/P) scheduling
- Recurring A/P bills are modeled as `payables.RecurringBillPlan` (weekly/monthly/yearly) with `next_run`, `is_active`, and optional `auto_post`.
- Generating bills:
  - Each run creates a new Bill with a single line item (expense account + configured amount).
  - Default due_date is the run date; user may edit after generation.
  - When `auto_post` is enabled, the bill is posted automatically.
- Date math must be safe:
  - Month rollovers clamp to the last day of the target month (e.g., Jan 31 → Feb 28/29).
  - Year rollovers handle leap day safely (Feb 29 → Feb 28 on non-leap years).
- Operations:
  - `Run now` is a forced generation action available to Managers.
  - `run_recurring_bills` management command generates all due bills (next_run <= today), with optional company filter.

## 2026-02-15 — Admin URL reverses in templates
- If a template uses an admin reverse like `admin:<app>_<model>_changelist`, the model **must** be registered in that app’s `admin.py`.
- For the Service Catalog, we keep the “Manage services” link pointing to the Admin changelist for speed, so `catalog.CatalogItem` is registered.

## 2026-02-15 — 2FA policy is optional and company-enforced
- 2FA is **optional** platform-wide.
- Enforcement is controlled by company settings and/or per-employee flags:
  - `Company.require_2fa_for_all`
  - `Company.require_2fa_for_admins_managers`
  - `Employee.force_2fa`
- When required, users are step-up challenged on company-scoped pages.

## 2026-02-15 — 2FA is optional; enforced only via settings

- 2FA is optional platform-wide.
- Enforcement occurs only through:
  - `Company.require_2fa_for_all`
  - `Company.require_2fa_for_admins_managers`
  - `EmployeeProfile.force_2fa`
- There is no automatic role-based forcing outside of those settings.

## 2026-02-15 — Time tracking is project-driven (client derived)

- If a project is selected on a time entry (or timer state), the client is derived from `project.client`.
- Mismatched project/client combinations are blocked.
- Legacy/manual entries may set client without a project for backward compatibility.

## 2026-02-15 — Catalog is first-class in-app (Manager+)

- Catalog Items (Services/Products) are manageable in-app for Manager+.
- Admin remains available, but day-to-day operations should not depend on Django admin.


## Money UX standard — Expenses/Payables/Payments (Phase 7H1)

**Decision**
- All monetary values are stored as **integer cents** in the database.
- All monetary inputs in UI use the shared `core.forms.money.MoneyCentsField` and render as **$xx.xx**.
- Templates should use `|money` for displaying any cents value.

**Scope shipped**
- Expenses, Payables, Payments forms converted to cents-backed fields (no float conversions).


### Invariants checks (Ops)
- We ship a built-in management command `ez360_invariants_check` to validate core financial invariants (invoice totals and payment rollups).
- This is intended to run in CI and/or as a pre-deploy sanity check in addition to `ez360_smoke_test`.

### Payment refunds (v1)
- Refunds are created from the Payment edit screen via `PaymentRefundForm`.
- Stripe refund execution is best-effort (requires Stripe config + charge/payment_intent IDs). If Stripe execution fails, the refund record is created and marked failed for manual processing.

## Timer: service on the fly (Catalog creation)
- When starting the global timer, users can select an existing service (CatalogItem) or type a custom service name.
- Manager+ users may optionally check **Save as catalog service** to create a new active CatalogItem(Service) with unit price $0.00 and non-taxable default.
- If a catalog service is selected, custom service name and save flag are ignored.

## Invariants Checks (Operational Policy)

- The management command `python manage.py ez360_invariants_check` is the canonical non-UI QA gate for financial integrity.
- It is safe to run in production (read-only) and should be used in CI and pre-deploy checks.
- `--quiet` is supported for CI-style output; failures exit with code 2.
- Scope (current):
  - Invoices: subtotal/tax/total sanity; paid/balance sanity; effective balance non-negative; credits applied bounds (warn)
  - Payments: refund bounds; refunded vs succeeded refunds (warn); net payment non-negative
  - Client credits: ledger sum vs `Client.credit_cents` (warn); credit application integrity (company/client match)
  - Journals: balance (debits == credits) and provenance sanity (source_type implies source_id)


## Refund journal proration (PaymentRefund → JournalEntry)
- Refund journals are posted idempotently via `JournalEntry(company, source_type="payment_refund", source_id=refund.id)`.
- Allocation between A/R debit and Customer Credits debit is pro-rated to match the original payment journal allocation.
- Pro-ration uses integer math (`(amount * ar_credited) // base`) to avoid float drift; remainder goes to credits.

## Ops Readiness Gate (CLI + UI)
- We maintain a **non-destructive readiness gate** that can be run via CLI (`python manage.py ez360_readiness_check`) and via Ops UI.
- The readiness check must never mutate business data; it may create and delete a tiny `.write_test` file in `MEDIA_ROOT` when using local storage.
- In production (`DEBUG=False`), email backend connectivity failures are treated as a **FAIL**; in development, email failures are reported as **OK (dev)** to avoid blocking local work.


## 2026-02-16 — Phase 7H10 Decisions

- Transactional emails must use `templates/emails/base.html` with `support_email` sourced from `settings.SUPPORT_EMAIL` (fallback `support@ez360pm.com`).
- Core pages should include contextual Help links to the relevant Help Center article.


## Ops Checks Evidence Policy
- Staff-run ops checks (smoke/invariants/idempotency/readiness) are persisted as OpsCheckRun for launch evidence.
- Ops checks support optional company scoping; quiet/fail-fast options apply where supported.
- Ops checks persistence must never break staff UI (best-effort logging).

## Timer shortcuts
- When a project is selected in the timer state, show an "Open selected project" shortcut (non-destructive) in both the navbar timer dropdown and the timer page.
- Shortcut is visible to any authenticated user with access to the timer UI (company-scoped).

## Currency display standard
- Canonical template filter for currency output is `|money` (formats integer cents as `$x,xxx.xx`).
- Legacy filter `|cents_to_dollars` remains supported but must render the same corporate format.
- All monetary values are stored as integer cents; the display standard does not change storage.


## Email Subject Standard (Corporate)
- All outbound email subjects must be passed through `core.email_utils.format_email_subject()`.
- Policy:
  - Trim whitespace.
  - Apply `EMAIL_SUBJECT_PREFIX` unless already prefixed.
  - Optional `EMAIL_SUBJECT_SEPARATOR` may be used for controlled joining.
  - Enforce a 200-character cap.

## Ops Evidence Output Policy
- OpsCheckRun output is stored with a hard cap (200k chars) and appends an explicit `[output truncated]` marker when truncated.
- Staff can download OpsCheckRun output as a `.txt` artifact from Ops → Checks.

## 2026-02-16 — Phase 7H15 Decision: Seat limits are computed
- Do not access `CompanySubscription.seats_limit` (not a model attribute).
- Seat limits must be derived via `billing.services.seats_limit_for(subscription)` (plan base seats + extra seats).

## 2026-02-16 — Phase 7H16 Decision: Money filter usage
- Templates that use `|money` must load `{% load money %}` explicitly.
- `|money` is the preferred currency display filter across the app (comma + 2 decimals).

## 2026-02-16 — Phase 7H17 Decision: Ops company URLs use UUIDs
- `Company.id` is a UUID.
- Ops routes that accept a company identifier must use the Django UUID path converter (`<uuid:company_id>`).


## Template sanity check policy
- Templates using `|money` must include `{% load money %}`.
- Avoid parentheses in `{% if %}` expressions; use nested ifs.
- Ops staff can run `ez360_template_sanity_check` from Ops → Checks.

## Template Filters Policy (money)
- Any template that uses `|money` or `|money_cents` MUST include `{% load money %}`.
- The `ez360_template_sanity_check` command enforces this.

## URL Sanity Checks (Templates)

- Templates should use `{% url %}` with valid named routes.
- We enforce a best-effort check via `python manage.py ez360_url_sanity_check` and expose it in Ops → Checks.
- CI/ops policy: failing URL sanity blocks production deploy until corrected.

## 2026-02-16 — Phase 7H22 Decision: Ops “Run all” behavior
- Ops Checks provides a **Run all** option for staff convenience.
- If no company is selected, **Smoke Test is skipped** (company-scoped).

## 2026-02-16 — Phase 7H22 Decision: Help Center must be reachable from the sidebar
- Help Center is considered core UX and must be reachable from the main left navigation.

## 2026-02-16 — Phase 7H23 Decisions

### Template sanity: CSRF + URL namespacing warnings
- POST forms should include `{% csrf_token %}`. The template sanity command warns when it detects a POST form without a token.
- Prefer namespaced URL names (e.g. `app:view_name`). The template sanity command warns when `{% url %}` uses an un-namespaced view name (heuristic, warn-only).

### Ops evidence export bundle
- Staff can export recent ops check runs as a ZIP artifact containing `runs.csv` plus per-run output text files.
- Export is staff-only and intended for launch evidence / audit trails.



## OpsCheckRun retention + scheduled evidence (2026-02-16)
- Ops check evidence is persisted in `ops.OpsCheckRun` and should be collected automatically.
- Daily scheduled job:
  - Run `python manage.py ez360_run_ops_checks_daily` (global checks; optionally include `--company-id` for company-scoped checks).
- Retention:
  - Run `python manage.py ez360_prune_ops_check_runs --days 30` to delete older evidence while protecting recent-per-kind runs.
- Rationale: keep launch evidence + regression tracking without unbounded DB growth.

## Help Center: A/R topics
- Help Center includes first-class A/R documentation pages: Accounts Receivable, Client Credits, and A/R Aging.
- Financial reports should include contextual Help links when available.

## Help Center: Collections/Statements + Report interpretation (2026-02-16)
- Corporate-grade finance UX requires explicit “what does this mean?” guidance in-product.
- Help Center includes Collections, Statements, and Report interpretation pages as part of the launch manual.

## Help Center: A/P Aging contextual help (2026-02-16)
- The A/P Aging report must include a contextual Help link to the Help Center A/P Aging article.

## Help Center: Production runbook (2026-02-16)
- The Help Center must include a Production Runbook page covering deploy checks, daily ops routines, scheduling options, and incident workflow.

## Ops Checks presets
- **Run recommended** runs: Readiness, Template sanity, URL sanity, Invariants, Idempotency. Smoke runs only when a company is selected.

## Template tag loading policy
- If a template uses `|money` / `|money_cents`, it must include `{% load money %}`.
- If a template uses humanize filters (e.g., `|intcomma`, `|naturaltime`), it must include `{% load humanize %}`.


## 2026-02-16 — Phase 7H30

- Ops alert routing is **DB-backed** (Ops.SiteConfig singleton) so staff can change webhook/email recipients without redeploying.
- Client Statements default to **open invoices only** (exclude Paid/Void) for the initial collections workflow.
- Statement PDF export is **optional** and only enabled when WeasyPrint is installed (lazy import / graceful fallback).

## 2026-02-16 — Statements links + APP_BASE_URL

- Introduced `APP_BASE_URL` (env-driven) to build absolute links in outbound emails and generated PDFs. If unset, emails/PDFs omit deep links.
- Client Statements support optional date-range filtering by invoice `issue_date` (fallback to `created_at` date when `issue_date` is missing). Exports honor the same filter.
- Ops alerts now have a staff detail view and a dashboard-driven “test alert” source (`ops_dashboard`) for routing verification.

## 2026-02-16 — Phase 7H32: Email attachments + statement delivery

- `core.email_utils.EmailSpec` supports optional attachments (filename, bytes, mimetype). Default is none to preserve existing call-sites.
- Statement emails may optionally include a PDF attachment when WeasyPrint is installed.
- Alert details support a “Copy JSON” affordance to speed up support tickets and debugging.

## 2026-02-16 — Phase 7H33: Statement email preview + Ops JSON download

- Statement delivery includes a **non-sending preview** endpoint so staff can validate subject/body before emailing a client.
- Statement PDF export failures should be actionable: distinguish **WeasyPrint not installed** vs **system dependency/render failure**.
- Ops alerts must support **exportable JSON** (download as file) and display a best-effort **Request ID correlation** when present.

## 2026-02-16 — Phase 7H34: Statements + Help Center + Ops triage affordances

- Statements page must surface **inline warnings** when:
  - `APP_BASE_URL` is not set (deep links in emails/PDFs are omitted).
  - WeasyPrint is not installed (PDF export / attachments unavailable).
  Rationale: prevent staff from assuming a broken workflow when it is an environment limitation.

- Help Center screenshot areas should use **consistent card-based placeholders** (static images) rather than raw "[Screenshot: ...]" text blocks.
  Rationale: the Help Center is part of the launch manual; placeholders must still look intentional.

- Ops Alerts triage should support **one-click quick-filters** via querystring parameters (status/source/level).
  Rationale: keep URLs shareable/bookmarkable and compatible with staff workflows.


## Statements: recipient defaults per client (Phase 7H35)

- We remember the last-used **statement recipient email** per Client, scoped to Company.
- Purpose: speed up collections workflows when clients want statements sent to a billing email that differs from the primary contact email.
- Storage: `documents.ClientStatementRecipientPreference`.


## Statement reminders (v1)
- Reminders are stored as DB records (StatementReminder) and executed by a periodic management command.
- v1 is manual scheduling (staff-driven); automation can be layered later using the same hook.


## Statement reminders: reminder tone presets (Phase 7H37)
- Reminders support two presets:
  - `friendly` (Friendly nudge)
  - `past_due` (Past due)
- The preset controls the email subject line + templates while reusing the same statement link and optional PDF attachment.


## Statement reminders: cadence helper + last-sent visibility (Phase 7H38)

- The Statement page provides **quick-pick cadence suggestions** for scheduling reminders:
  - In 3 days / In 7 days / In 14 days
  - Next Monday
  - End of month
- The Statement page shows a **Last sent** table (recent SENT reminders) to give staff immediate visibility into recent outreach.
- Default reminder recipient resolution order (UI default):
  1) last-used session value (`stmt_to_<client_id>`)
  2) saved per-client preference (`ClientStatementRecipientPreference.last_to_email`)
  3) `Client.email`


## Statement reminders: attempt tracking + failed reschedule (Phase 7H39)

- Every reminder send attempt records:
  - `attempted_at` (timestamp)
  - `attempt_count` (counter)
  Rationale: failures must be debuggable without digging through host logs.

- Rescheduling a FAILED reminder:
  - sets `status=SCHEDULED`
  - clears `last_error`
  - clears `sent_at`
  Rationale: keep the model simple; attempt metadata remains historical context while the reminder is retried.


## Statement reminders: retry now + reschedule-to-date (Phase 7H40)

- Failed reminder rescheduling supports an optional **date input** (if blank, default remains +7 days).
  Rationale: staff often want to align follow-ups to a specific day (e.g., next pay cycle) without extra clicks.

- Added **Retry now** action (staff-only) that performs a synchronous send attempt and records attempt metadata.
  Rationale: support workflows need a one-click "try again" after fixing email configuration or recipient issues; restricting to staff prevents accidental spam by normal users.

- Ops scheduler warnings expanded to include Stripe/storage/domain readiness.
  Rationale: reduce "silent misconfiguration" risk before going live by surfacing common production gaps on the Ops Dashboard.


## Statements: “Email me a copy” + reminder audit trail (Phase 7H41)

- Statement email send includes an optional **“Email me a copy”** checkbox.
  - If enabled, the app sends a best-effort copy to the acting user’s email with subject prefix `Copy ·`.
  - Copy send is intentionally secondary and must never block the primary client send.

- Reminder audit trail is captured with:
  - `created_by` (who scheduled)
  - `modified_by` (who last changed)
  - `updated_at` (when last changed)
  Rationale: collections workflows require accountability without adding heavyweight history tables.


## Ops alerts: dedup + snooze (Phase 7H41)

- Ops alert creation supports:
  - **Dedup window** (SiteConfig `ops_alert_dedup_minutes`) for identical open alerts.
  - **Snooze** (OpsAlertSnooze) per source and optional per-company scope.
  Rationale: reduce alert spam while retaining a durable record of the first occurrence.


## Statement reminders: bulk send-now + delivery report (Phase 7H43)

- Bulk **Send now** is restricted to **Django staff OR company admin/owner** and is capped (200 reminders) to prevent accidental spam.
  Rationale: collections workflows need a fast “push now” button, but it must be guarded and rate-limited.

- Reminder delivery report is computed from `attempted_at` (not `scheduled_for`) and grouped by day for the last 30 days.
  Rationale: attempted-at reflects actual delivery work; scheduled-for reflects intent.

## Ops dashboard: open alert grouping summary (Phase 7H43)

- Ops Dashboard includes an “Open alerts summary” grouped by **source** and **source+company** (top 25).
  Rationale: staff can quickly identify the noisiest source/company pairs without combing the full alerts list.


## 2026-02-16 — Phase 7H44
- Statement reminders bulk sending supports **selected IDs** and **filtered set**; filtered sends require an explicit confirm checkbox and are safety-capped at 200 to prevent accidental mass sends.
- Statement activity tracking is best-effort and must never block collections workflows.
- Ops dashboard deep links prefer `company_id` filtering over company-name search to avoid ambiguity.


## 2026-02-16 — Phase 8A (UI Foundation)

- **No framework switch.** We keep Bootstrap 5 and harden the existing design language.
  Rationale: Phase 8 is launch prep; we want predictable CSS and minimal regressions.

- **Global card standard:** pages use Bootstrap cards, and `card shadow-sm` is treated as the app-standard surface.
  Rationale: consistent surfaces increase perceived quality without template-by-template rewrites.

- **Sidebar active state is automatic (JS).** We compute the best matching link by URL prefix.
  Rationale: avoids brittle per-view “active tab” context plumbing.

- **Typography helpers are additive.** Use `.ez-page-title`/`.ez-page-subtitle` instead of inventing new heading scales per template.
  Rationale: consistent hierarchy for accounting-heavy screens.


## 2026-02-16 — Phase 8B (Dashboard)

- Dashboard KPIs are “finance-first” and must be explainable:
  - Revenue = succeeded payments within month (net of refunds when available).
  - Expenses = expense totals by date range.
  - A/R = sum of open invoice balances.
  - Unbilled time = approved billable minutes not yet billed.
  Rationale: numbers must align with accounting expectations; avoid vanity metrics.


## 2026-02-16 — Phase 8C (Tables)

- Action columns use **icon + dropdown** rather than multiple text buttons.
  Rationale: increases information density without looking cluttered, and keeps tables readable on smaller screens.

- Document status colors are centralized in a template filter (`doc_status_badge_class`).
  Rationale: prevents drift across templates and makes future tweaks a one-file change.

