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
    path("help/storage-files/", views.help_storage_files, name="storage_files"),
    path("help/billing/", views.help_billing, name="billing"),
    path("help/ops/", views.help_ops, name="ops"),
    path("help/ops-console/", views.help_ops_console, name="ops_console"),
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
