# EZ360PM Phase 9 — Feature-by-Feature QA + Fix Plan

**Date:** 2026-02-17  
**Purpose:** Run a disciplined, feature-by-feature validation of EZ360PM for v1 launch readiness. For each feature we will:
1) confirm intended behavior, 2) test it end-to-end, 3) decide v1 readiness, 4) fix gaps immediately (or explicitly defer).

This plan is designed to be executed **iteratively**: we review one feature at a time, log results, apply a cohesive fix pack when needed, and update docs.

---

## Guiding Rules

### The QA loop (applies to every feature)
For each feature/module:

1. **Spec (Expected Behavior)**
   - What it does
   - Roles/permissions (Owner/Admin/Manager/Staff)
   - UI entry points (nav, buttons, links)
   - Data invariants (especially money + accounting)
   - Settings involved (Site/Company settings, Stripe/Plaid toggles)

2. **Acceptance Checks (Pass/Fail)**
   - Happy path
   - Edge cases (permissions, empty states, double-submit, invalid input, deletions)
   - Observability (audit events, logs, error handling)

3. **V1 Readiness Decision**
   - ✅ **V1 Approved** — correct and shippable
   - 🟡 **V1 Approved w/ Polish** — minor UI/wording/empty-state improvements
   - 🔴 **Must Fix Before Launch** — correctness/security/data integrity/financial issues
   - 🔵 **Defer** — non-essential improvements; documented in roadmap

4. **Fix Immediately If Needed**
   - Implement cohesive fix pack (code + templates + tests)
   - Add/adjust tests for the defect class
   - Update docs (this plan + feature inventory + roadmap + memory)

---

## QA Artifacts We Maintain

### 1) QA Ledger (living table)
We track each feature using this table (keep updated as we go):

| Feature | Owner (role) | Acceptance Checks | Status | Findings | Fix Pack | V1 Decision |
|---|---|---|---|---|---|---|
| Access & Roles | Owner/Admin | Login, verify, role gates | ☐ |  |  |  |

**Status values:** ☐ Not started / ▶ In progress / ✅ Pass / ❌ Fail / 🟡 Pass w/ polish / 🔵 Deferred

### 2) Feature Inventory Expansion
The authoritative detailed “how it works” docs live in `docs/FEATURE_INVENTORY.md`.
Each feature section is expanded with:
- Step-by-step flows
- Screens involved
- Roles
- Settings
- Expected audit events
- Edge cases

### 3) Fix Packs
When failures are found, we implement changes as **Fix Packs**:
- Pack name: `P9-<area>-<short-desc>` (example: `P9-TIME-TimerDropdown`)
- Includes: code + templates + tests + doc updates
- Each pack ends with: “What changed / What to retest / Remaining risks”

**Recent Fix Packs**
- `P9-UI1` — UI consistency sweep + boot fixes (Integrations import alias, QA index name hardening, remaining card standardization)

---

## QA Environment Standard (so results are repeatable)

### Recommended setup
- Run locally **and** verify on Render staging/production-like environment.
- Use one consistent dataset so results are comparable.

### Seed dataset (minimum)
- 2 Companies: **Company A** and **Company B** (to validate isolation)
- Users per company: Owner, Admin, Manager, Staff
- Sample data:
  - 5 Clients
  - 8 Projects (mix: hourly, flat, retainer if present)
  - Time entries across states: draft/submitted/approved/billed
  - 3 Estimates, 3 Invoices (draft/sent/paid/void)
  - Payments: partial + overpayment credit case
  - Expenses with at least 2 receipts
  - Vendors/Bills (if payables enabled)
  - Accounting seeded chart of accounts + posted entries from actions above

---

## Execution Order (highest risk first)

> Order matters: we front-load launch blockers (security, company isolation, money correctness).

### 0) Foundations: Access, Company Context, Role Enforcement (Launch Blockers)
**Goal:** Prove the app is safe and isolated per company and per role.
- Auth: login/logout/register/reset
- Email verification (if enforced)
- 2FA (if present)
- Rate limiting / throttle rules
- Active company selection/switching
- Sidebar/topbar visibility rules

**Must-fix triggers:**
- Any cross-company data leak
- Any role bypass
- Any lockout that blocks admin operations

---

### 1) Navigation + App Shell + Help/Legal Discoverability
- Public vs app shell
- Sidebar links (no dead ends)
- Help Center entry points
- Terms/Privacy pages accessible

**Must-fix triggers:**
- 404/500 links from navigation
- missing legal pages for launch

---

### 2) CRM: Clients
- List/search/pagination
- Create/edit/delete
- CSV import/export (if included)
- Audit events and permission scoping

---

### 3) Projects
- Staff scoping
- Billing types + rate inputs (dollars formatting)
- Project services linkage
- Project → unbilled time → invoice conversion

---

### 4) Time Tracking (High-traffic / High-risk)
- Global timer dropdown flow
- Manual time entry
- State machine (draft/submitted/approved/billed)
- Manager approvals (if enabled)
- Billing linkage + immutability

**Must-fix triggers:**
- incorrect state transitions
- billed time not locked / can be edited incorrectly
- timer dropdown broken (core workflow)

---

### 5) Catalog (Services/Items)
- CRUD permissions
- Appears correctly in forms (time + documents)
- Correct labeling and consistent usage

---

### 6) Documents: Estimates / Invoices / Proposals
- Status transitions + immutability rules
- Line items + tax calculations
- Numbering tokens/templates
- PDF/email generation behavior

**Must-fix triggers:**
- incorrect totals
- sent/paid documents editable
- broken pdf/email dispatch paths

---

### 7) Payments (Stripe + manual) + Credits + Reconciliation
- Partial payments
- Overpayment → credit ledger
- Stripe checkout/webhooks (idempotency)
- Audit coverage

**Must-fix triggers:**
- financial math incorrect
- webhook non-idempotent or unsafe
- credits not accurate

---

### 8) Expenses
- CRUD + receipt upload/view
- Correct totals in accounting
- Permissions correct

---

### 9) Payables (Vendors, Bills, Recurring Bills)
- Vendors
- Bills + attachments
- Recurring schedules (if present)

**Must-fix triggers:**
- module linked in nav but non-functional
- vendor collisions / broken relations

---

### 10) Accounting Engine (Trust Engine)
- Chart of Accounts per company
- Posting rules (idempotent)
- Reports: P&L, Balance Sheet, Trial Balance, GL, Aging
- Reconciliation views (Phase 9 focus)

**Must-fix triggers:**
- double-posting
- cross-company ledger bleed
- incorrect report math

---

### 11) Audit Logs
- Coverage for critical actions (money, settings, access)
- Role visibility

---

### 12) Ops / Monitoring / Retention
- health/version
- ops alerts and retention pruning
- Sentry wiring (if configured)

---

### 13) Storage & Integrations
- Local vs S3 media rules
- Signed access behavior (if implemented)
- Plaid “ready” wiring (gated if not live)

---

### 14) Launch Gate Checklist
- final smoke test script (Owner + Staff)
- v1 “known limitations” list
- backup/restore verification
- environment variables validation

---

## How We Start (First Session)

We start with **Feature 0**: Access + Company Context + Roles.

Output of the first session:
- QA Ledger rows for Feature 0 (Pass/Fail)
- Any Fix Pack(s) created
- Updated `FEATURE_INVENTORY.md` sections for Feature 0
- Roadmap updated with what was validated and what remains

---

## Where to Record Results
- QA outcomes per feature: add to the **QA Ledger** section in this file
- Detailed steps and flows: `docs/FEATURE_INVENTORY.md`
- What changed and why: `docs/MEMORY.md`
- Anything deferred: `docs/ROADMAP.md`

