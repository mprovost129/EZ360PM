from django.urls import path

from . import views

app_name = "accounting"

urlpatterns = [
    path("accounting/", views.accounting_home, name="home"),
    path("accounting/profit-loss/", views.profit_loss, name="profit_loss"),
    path("accounting/balance-sheet/", views.balance_sheet, name="balance_sheet"),
    path("accounting/trial-balance/", views.trial_balance, name="trial_balance"),
    path("accounting/general-ledger/", views.general_ledger, name="general_ledger"),
    path("accounting/reconciliation/", views.reconciliation, name="reconciliation"),
    path("reports/", views.reports_home, name="reports_home"),
    path("reports/revenue-by-client/", views.revenue_by_client, name="revenue_by_client"),
    path("reports/project-profitability/", views.project_profitability, name="project_profitability"),
    path("reports/accounts-aging/", views.accounts_aging, name="accounts_aging"),
]
