"""Default Launch Gate checklist items.

These are intentionally high-level. They are a human process companion to the
automated launch checks at /ops/launch-checks/.

Staff can add/edit items in Django admin if desired. This list is used only for
initial seeding.
"""

from __future__ import annotations


DEFAULT_LAUNCH_GATE_ITEMS = [
    {
        "key": "env-prod-ready",
        "title": "Production environment configured",
        "description": "DEBUG=False, APP_BASE_URL set, ALLOWED_HOSTS/CSRF trusted origins correct, secret keys present.",
    },
    {
        "key": "email-delivery",
        "title": "Email delivery verified",
        "description": "SMTP provider configured, test email delivered, From/Reply-To policies confirmed.",
    },
    {
        "key": "stripe-subscriptions",
        "title": "Stripe subscriptions verified",
        "description": "Checkout, portal, webhooks, trial rules, plan mapping, and seat limits validated.",
    },
    {
        "key": "payments-invoices",
        "title": "Invoice → payment loop verified",
        "description": "Create invoice, pay via Stripe, status updates, journal entries, A/R and aging correctness.",
    },
    {
        "key": "storage-media",
        "title": "Storage/media verified",
        "description": "Uploads work (local/S3 per config), permissions correct, backups location confirmed.",
    },
    {
        "key": "ops-monitoring",
        "title": "Ops monitoring enabled",
        "description": "Ops checks scheduled (cron), alert routing configured, healthz endpoint monitored.",
    },
    {
        "key": "legal-pages",
        "title": "Legal pages reviewed",
        "description": "Terms, privacy, cookies, security pages present and linked publicly.",
    },
    {
        "key": "role-permissions",
        "title": "Roles/permissions sanity pass",
        "description": "Owner/admin/manager/staff access verified across CRM, documents, accounting, and ops.",
    },
]
