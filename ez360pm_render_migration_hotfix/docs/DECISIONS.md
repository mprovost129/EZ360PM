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
