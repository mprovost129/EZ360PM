# EZ360PM v1 Production Baseline

This document locks the scope and operational contract for the v1 launch.

## Included in v1

- Multi-company tenancy (active company context, isolation)
- Role-based access (staff / manager / admin / owner)
- Clients
- Projects
- Time tracking (timer + entries)
- Documents: Proposals, Estimates, Invoices
- Payments (partial payments, credits)
- Expenses
- Accounting engine (Chart of Accounts, Journals, P&L, Balance Sheet, Trial Balance, GL)
- Stripe subscriptions (trial, plan tiers, seat limits, gating)
- Audit logging (financial + sensitive actions)
- Legal pages (Terms, Privacy, Security)
- Monitoring (Sentry) + basic ops endpoints

## Not in v1

- Multi-currency
- Payroll
- Inventory
- Advanced analytics/BI dashboards
- Enterprise SSO / SCIM
- Complex approval workflows beyond current role gates

## Non-negotiables

- Financial invariants: totals, posting, and status transitions are idempotent and transaction-safe.
- Tenant isolation: all company-scoped queries must be filtered by active company.
- Production safety: DEBUG off, secure cookies, CSRF origins configured.
