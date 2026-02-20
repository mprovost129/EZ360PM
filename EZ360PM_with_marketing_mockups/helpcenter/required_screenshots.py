"""helpcenter/required_screenshots.py

Phase 7H46:
- Maintain an explicit checklist of Help Center screenshot keys that should exist.
- Used by Django Admin to show completeness / missing uploads.

Why this is a constant and not auto-discovered:
- Template scanning at runtime is brittle in production and can miss dynamically loaded templates.
- We want a stable, reviewable list that changes only when we add/rename screenshots.
"""

from __future__ import annotations


# NOTE: Keep this in sync with `hc_screenshot` usages in Help Center templates.
REQUIRED_HELP_SCREENSHOT_KEYS: list[str] = [
    # Accounting
    "accounting_overview",
    "chart_of_accounts",
    "journal_entries",
    "reports_index",
    "general_ledger",
    "profit_loss",
    "balance_sheet",
    "trial_balance",
    # Time
    "time_tracking",
    "timer_navbar",
    "time_entries_list",
    "time_approval_queue",
    # Invoices & Payments
    "invoices_payments",
    "invoices_payments_list",
    "invoice_editor",
    "record_payment",
    "client_credit_applied",
    # Statements
    "statements_table",
    "statements_actions",
    "statements_email",
]
