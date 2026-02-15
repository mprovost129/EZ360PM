# Ops Retention & Pruning

EZ360PM stores some operational data that can grow over time (audit log, Stripe webhook payloads). This pack adds a simple retention policy and prune tooling.

## What gets pruned

1) **Audit events** (`audit.AuditEvent`)
   - Per-company audit log entries
   - Pruned using: `EZ360_AUDIT_RETENTION_DAYS` (default 365)

2) **Stripe webhook events** (`billing.BillingWebhookEvent`)
   - Stored webhook payload JSON
   - Pruned using: `EZ360_STRIPE_WEBHOOK_RETENTION_DAYS` (default 90)

## Run manually

Dry-run (counts only):

```bash
python manage.py ez360_prune
```

Execute deletes:

```bash
python manage.py ez360_prune --execute
```

## Ops UI

Staff can view retention policy and run prune from:

- **Ops → Retention** (`/ops/retention/`)

## Scheduling (recommended)

Run nightly via cron or your host’s scheduled jobs.

Example cron (02:15 daily):

```cron
15 2 * * * /path/to/venv/bin/python /srv/ez360pm/manage.py ez360_prune --execute
```

## Notes

- Pruning uses **bulk deletes**, so rows are permanently removed.
- Adjust retention windows based on your compliance needs.
