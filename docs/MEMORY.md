# EZ360PM — Project Snapshot

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
