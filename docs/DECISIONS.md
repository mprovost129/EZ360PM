# EZ360PM — Locked Decisions (Post Phase 3A)

## 2026-02-13 — Security defaults are production-on (Phase 3R)

- Email verification gate defaults **ON** when `DEBUG=False` (override via `ACCOUNTS_REQUIRE_EMAIL_VERIFICATION`).
- Company onboarding defaults to require **2FA for managers/admins/owners** in production (override via `COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS`).
- `SECURE_SSL_REDIRECT`, secure cookies, and HSTS default ON in production.


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
