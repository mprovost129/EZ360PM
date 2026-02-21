# EZ360PM Manual QA Checklist (Launch Gate)

This checklist is meant to be executed **top-to-bottom** on **staging** (Render) and once more on **production** immediately before launch.

Conventions:
- ✅ = pass
- ❌ = fail (log a ticket; fix before launch)
- ⚠️ = acceptable known limitation (must be documented)

---

## 0) Environment & Preflight

- [ ] Confirm `DEBUG=False` on staging/prod (no debug toolbar, no detailed tracebacks).
- [ ] Confirm `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` match the live domains.
- [ ] Confirm `/health/` returns `200` and `{"status":"ok"}`.
- [ ] If `HEALTHCHECK_TOKEN` is set: `/health/details/` returns `200` with token, otherwise `404/403`.
- [ ] Confirm Sentry is receiving events (use the Sentry test route/tool if present).
- [ ] Run: `python manage.py ez360_preflight` (must pass).
- [ ] Run: `python manage.py ez360_invariants_check` (must pass).
- [ ] Run: `python manage.py ez360_template_sanity_check` (must pass).

---

## 1) Auth, Onboarding, Companies

- [ ] Register a new user (recaptcha works, email flow OK if enabled).
- [ ] Login/logout works; session persists across refresh.
- [ ] On first login: onboarding creates company (or prompts to create/select).
- [ ] Company switcher:
  - [ ] Switching company changes visible data (clients/projects/docs).
  - [ ] Active company persists after refresh.
- [ ] Invite flow (if enabled):
  - [ ] Invite user receives email
  - [ ] Accept invite → access limited to invited company

---

## 2) Roles & Permissions

For each role (staff / manager / admin / owner):
- [ ] Navigation shows only allowed items.
- [ ] Forbidden URLs return 403 (not 500).
- [ ] Staff cannot access: billing admin, webhook logs, audit exports (as applicable).

---

## 3) Clients

- [ ] Create client (address, phone/email; state dropdown matches styling).
- [ ] Edit client; changes persist.
- [ ] Delete client (soft/hard per design) — project/doc linkage behaves correctly.
- [ ] Search clients by name/email/company.
- [ ] CSV import (if present) and export:
  - [ ] Import invalid row → error shown but rest imports.
  - [ ] Export includes expected columns.

---

## 4) Projects

- [ ] Create project with client.
- [ ] Billing type:
  - [ ] Hourly: rate is **$xx.xx** (not cents) in UI.
  - [ ] Flat: rate is **$xx.xx** in UI.
- [ ] Assign staff to project (if feature exists).
- [ ] Project list filters/search work.
- [ ] Project detail shows linked docs, time, invoices.

---

## 5) Time Tracking

Timer:
- [ ] Navbar timer opens dropdown reliably (desktop + mobile).
- [ ] Project dropdown shows project number + name (not "Project object").
- [ ] Service dropdown pulls from catalog/service list.
- [ ] Notes field saves.
- [ ] Start → stop creates a time entry with correct duration.

Time entry lifecycle (if approvals enabled):
- [ ] Draft → submitted
- [ ] Manager approves
- [ ] Approved time can be billed to an invoice
- [ ] Billed time entries are locked (or clearly marked)

---

## 6) Catalog / Services

- [ ] Create a service item.
- [ ] Service appears in document line item dropdowns.
- [ ] Tax behavior (taxable / non-taxable) behaves as expected.

---

## 7) Documents (Proposal / Estimate / Invoice)

### 7.1 Document composer UX (“paper editor”)
- [ ] Create Invoice opens paper-like editor.
- [ ] Header:
  - [ ] Company logo (safe if missing)
  - [ ] Company address/contact
- [ ] Client selection uses dropdown from client list.
- [ ] Project selection uses dropdown from project list.
- [ ] Document number/date fields editable and validate.
- [ ] Line items:
  - [ ] Add line works
  - [ ] Remove line works
  - [ ] Reorder (if enabled) works
  - [ ] Real-time totals update (subtotal/tax/total/balance)
- [ ] Deposit:
  - [ ] by percent works
  - [ ] by fixed amount works
- [ ] Notes section saves.
- [ ] Terms:
  - [ ] Invoice terms show
  - [ ] Proposal/Estimate terms behavior matches design

### 7.2 Document workflow
- [ ] Save draft.
- [ ] Mark sent (or send email if enabled).
- [ ] Print/PDF:
  - [ ] PDF renders and matches on-screen layout.
  - [ ] Totals/tax show correctly.
- [ ] Payments:
  - [ ] Partial payment updates balance + status.
  - [ ] Full payment marks paid.
  - [ ] Overpayment creates credit ledger entry (if implemented).
- [ ] Delete/void behavior matches design (and posts correct journals).

---

## 8) Payments

- [ ] Record manual payment against invoice.
- [ ] Stripe Checkout payment (if enabled) updates invoice and ledger idempotently.
- [ ] Payment list shows correct totals and filters.
- [ ] Refunds/voids (if present) behave correctly and post journals.

---

## 9) Expenses

- [ ] Create expense with merchant and amount.
- [ ] Receipt upload works (local + S3 prod).
- [ ] Approve / reimburse states work (if used).
- [ ] Expense posts correct journal entry and affects P&L.

---

## 10) Banking (Plaid / Review Queue) — if enabled

- [ ] Connect bank via Plaid.
- [ ] Transactions import.
- [ ] Duplicate prevention:
  - [ ] duplicate suggested link works
  - [ ] mark as reviewed works
- [ ] Reconciliation views load and totals match.

---

## 11) Accounting Reports

- [ ] Chart of accounts seeded correctly per company.
- [ ] Create invoice → posts journal lines correctly.
- [ ] Record payment → posts correctly.
- [ ] Create expense → posts correctly.
- Reports:
- [ ] Profit & Loss shows expected totals.
- [ ] Balance Sheet balances (Assets = Liabilities + Equity).
- [ ] Trial Balance matches journals.
- [ ] General Ledger filters work.

---

## 12) Billing & Subscription (Stripe)

- [ ] Trial enforcement works.
- [ ] Upgrade plan works.
- [ ] Add seat works (monthly + yearly if configured).
- [ ] Cancel subscription:
  - [ ] access changes according to policy (end of period)
- [ ] Customer portal opens (if enabled).
- [ ] Webhook logs accessible to staff-only admin role (as designed).

---

## 13) Help Center / Legal Pages / Footer

- [ ] Footer links: Privacy, Terms, Security, Support work on public and app shells.
- [ ] Legal pages render with correct content + last-updated date.
- [ ] Help pages load without requiring login (as designed).

---

## 14) Security & Abuse Hardening

- [ ] ScannerShield endpoints return:
  - [ ] `/.env` → 410 Gone
  - [ ] `/wp-login.php` → 410 Gone (if included)
- [ ] Rate limits trigger for repeated public POST actions (login/register) if configured.
- [ ] Permissions enforced server-side (no UI-only checks).

---

## 15) Error Pages & Fallbacks

- [ ] Custom 404 displays branded page.
- [ ] Custom 500 displays branded page (simulate in staging only).
- [ ] No page should raise 500 in normal navigation.

---

## 16) Post-Deploy Smoke (Production)

- [ ] Login works on production.
- [ ] Create client/project/document works.
- [ ] Generate a PDF works.
- [ ] `/health/` returns 200.
- [ ] Sentry receives at least one event.

---

## Optional: Seed Data Helper (Local)

If you want a quick dataset locally:

```bash
python manage.py seed_qa --company "EZ360PM Demo Co" --reset
```

This creates demo clients/projects/service + a draft invoice and a sample expense.
