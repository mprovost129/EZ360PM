# Launch Gate Checklist (v1)

Launch happens when this file is **all green**.

## A) Build + Deploy

- [ ] Render services configured (web + worker if used)
- [ ] Production env vars set (see `docs/ENV_VARS.md`)
- [ ] `DEBUG=False` in production
- [ ] `ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS` correct for www + apex
- [ ] `collectstatic` succeeds (no missing manifest entries)
- [ ] Migrations run cleanly on a fresh DB
- [ ] `/health/` returns 200 in production

## B) Security

- [ ] HTTPS enforced
- [ ] Secure cookies enabled (SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE)
- [ ] Staff/admin paths protected; no public admin exposure
- [ ] Scanner shield blocks common probes
- [ ] Password reset + email verification flow validated
- [ ] 2FA enforcement settings tested (if enabled)

## C) Tenant Isolation

- [ ] Cross-company access attempts blocked for Clients/Projects/Documents/Payments/Expenses
- [ ] Active company switcher updates session correctly
- [ ] Public token pages do not leak other-company data

## D) Money Loop

- [ ] Invoice totals match line items + tax + discounts
- [ ] Payments update balance due correctly
- [ ] Overpayments create credit entries and do not break invariants
- [ ] Accounting postings are idempotent and balanced

## E) Core UX Smoke

- [ ] Create client / project works end-to-end
- [ ] Timer start/stop and time entry submission works
- [ ] Create proposal/estimate/invoice “paper editor” works
- [ ] PDF export works for docs
- [ ] Footer legal links work

## F) Monitoring + Backups

- [ ] Sentry events captured in production
- [ ] DB backups configured + tested restore procedure documented
