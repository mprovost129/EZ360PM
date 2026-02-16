# EZ360PM Feature Inventory (Manual Skeleton)

> Source snapshot: `ez360pm_phase7g1_hotfix_admin_catalogitem.zip`  
> Date: 2026-02-15

This document is the **skeleton** for the corporate-grade “User Manual + QA Plan”.
Each section will be expanded with:
- Purpose
- Who can do what (Owner/Admin/Manager/Staff)
- Step-by-step user flows
- Settings involved
- Audit events and expected logs
- Edge cases / failure modes
- Acceptance checks

---

## 0) Product Overview
- CRM + Projects + Time + Documents + Payments + Accounting + Payables + Ops
- Multi-company with active-company context
- Role hierarchy: Owner / Admin / Manager / Staff
- Support mode for staff (restricted)

## 1) Access, Identity, Security
- Auth: register/login/logout/reset
- Email verification
- 2FA (optional, company enforced)
- Rate limiting / throttles
- Support mode

## 2) Company System
- Onboarding and company switcher
- Team roles / employees
- Company settings

## 3) Navigation + App Shell
- Public vs app layout
- Sidebar modules and role visibility
- Global timer dropdown
- Help Center entrypoints

## 4) CRM (Clients)
- List/search/pagination
- CRUD
- CSV import/export (if enabled)
- Audit events

## 5) Projects
- List + staff scoping
- CRUD: billing types + rates
- Services attached to project
- Project files + storage
- Conversions: unbilled time → invoice

## 6) Time Tracking
- Timer + manual entries
- State machine: draft/submitted/approved/billed
- Manager approvals
- Billing linkage to invoices

## 7) Catalog (Services/Items)
- Catalog items (service/product)
- Usage across time entries and documents
- Admin vs app UI surface

## 8) Documents (Estimates/Invoices/Proposals)
- Status flows
- Line items + taxes
- Numbering templates
- PDF/email delivery
- Immutability rules

## 9) Payments
- Manual + Stripe flows
- Partial payments + credits
- Reconciliation behavior

## 10) Expenses
- CRUD + receipts
- Posting to accounting

## 11) Payables
- Vendors
- Bills + attachments
- Recurring bills

## 12) Accounting Engine
- COA
- Journal posting invariants + idempotency
- Reports (P&L / BS / GL / Trial Balance / Aging)

## 13) Audit Logs
- Events by module
- Visibility rules

## 14) Ops / Observability
- healthz/version endpoints
- monitoring hooks
- error handling

## 15) Storage & Integrations
- Private media access + previews
- S3 strategy
- Dropbox integration (if enabled)
- Desktop sync endpoints (if present)

## 16) Help Center & Legal
- Help pages for each module
- Terms, Privacy, Cookies, AUP, Security, Refund policy

## 17) Launch Readiness Checklist
- Security checks
- Financial invariants checks
- Backup/restore drill
- Monitoring readiness
- E2E acceptance flow

---

## Static Code Check Notes (this snapshot)
### Fixed in this pack
- Help Center was not included in root routing → now included in `config/urls.py`.
- Top-nav Help button now points to Help Center.

### Still to do / verify
- TimeEntry UX should be project-driven; client should be derived (model currently has both).
- Catalog should become a first-class UI (not admin-only) for corporate usability.
- Dollar formatting consistency across all money inputs + admin list displays.

