from django.urls import path

from . import views


app_name = "helpcenter"


urlpatterns = [
    # Help center
    path("help/", views.help_home, name="home"),
    path("help/getting-started/", views.help_getting_started, name="getting_started"),
    path("help/roles-permissions/", views.help_roles_permissions, name="roles_permissions"),
    path("help/time-tracking/", views.help_time_tracking, name="time_tracking"),
    path("help/invoices-payments/", views.help_invoices_payments, name="invoices_payments"),
    path("help/accounting/", views.help_accounting, name="accounting"),
    path("help/profit-loss/", views.help_profit_loss, name="profit_loss"),
    path("help/balance-sheet/", views.help_balance_sheet, name="balance_sheet"),
    path("help/trial-balance/", views.help_trial_balance, name="trial_balance"),
    path("help/accounts-receivable/", views.help_accounts_receivable, name="accounts_receivable"),
    path("help/client-credits/", views.help_client_credits, name="client_credits"),
    path("help/ar-aging/", views.help_ar_aging, name="ar_aging"),
    path("help/collections/", views.help_collections, name="collections"),
    path("help/statements/", views.help_statements, name="statements"),
    path("help/report-interpretation/", views.help_report_interpretation, name="report_interpretation"),
    path("help/bills/", views.help_bills, name="bills"),
    path("help/vendor-credits/", views.help_vendor_credits, name="vendor_credits"),
    path("help/ap-reconciliation/", views.help_ap_reconciliation, name="ap_reconciliation"),
    path("help/ap-aging/", views.help_ap_aging, name="ap_aging"),
    path("help/storage-files/", views.help_storage_files, name="storage_files"),
    path("help/billing/", views.help_billing, name="billing"),
    path("help/ops/", views.help_ops, name="ops"),
    path("help/ops-console/", views.help_ops_console, name="ops_console"),
    path("help/production-runbook/", views.help_production_runbook, name="production_runbook"),
    path("help/recurring-bills/", views.help_recurring_bills, name="recurring_bills"),
    path("help/refunds/", views.help_refunds, name="refunds"),
    path("help/faq/", views.help_faq, name="faq"),

    # Legal
    path("legal/terms/", views.legal_terms, name="terms"),
    path("legal/privacy/", views.legal_privacy, name="privacy"),
    path("legal/cookies/", views.legal_cookies, name="cookies"),
    path("legal/acceptable-use/", views.legal_acceptable_use, name="acceptable_use"),
    path("legal/security/", views.legal_security, name="security"),
    path("legal/refund-policy/", views.legal_refund_policy, name="refund_policy"),
]
