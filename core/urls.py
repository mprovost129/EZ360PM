# core/urls.py
from __future__ import annotations

from django.urls import path

from . import views
from .views_onboarding import onboarding_company

app_name = "core"

urlpatterns = [
    # -----------------------------
    # Clients
    # -----------------------------
    path("clients/", views.clients_list, name="clients"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clients/<int:pk>/edit/", views.client_update, name="client_update"),
    path("clients/<int:pk>/delete/", views.client_delete, name="client_delete"),

    # -----------------------------
    # Projects
    # -----------------------------
    path("projects/", views.projects_list, name="projects"),
    path("projects/new/hourly/", views.project_create_hourly, name="project_create_hourly"),
    path("projects/new/flat/", views.project_create_flat, name="project_create_flat"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/edit/", views.project_update, name="project_update"),
    path("projects/<int:pk>/delete/", views.project_delete, name="project_delete"),
    path("projects/<int:pk>/timer/start/", views.project_timer_start, name="project_timer_start"),
    path("projects/<int:pk>/timer/stop/", views.project_timer_stop, name="project_timer_stop"),
    path("projects/<int:pk>/time/add/", views.timeentry_create, name="timeentry_create"),
    path("projects/<int:pk>/invoice-time/", views.project_invoice_time, name="project_invoice_time"),

    # -----------------------------
    # Invoices (private)
    # -----------------------------
    path("invoices/", views.invoices_list, name="invoices"),
    path("invoices/new/", views.invoice_create, name="invoice_create"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("invoices/<int:pk>/edit/", views.invoice_update, name="invoice_update"),
    path("invoices/<int:pk>/delete/", views.invoice_delete, name="invoice_delete"),
    path("invoices/<int:pk>/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("invoices/<int:pk>/email/", views.invoice_email, name="invoice_email"),
    path("invoices/<int:pk>/send/", views.invoice_send_email, name="invoice_send_email"),
    path("invoices/<int:pk>/mark-sent/", views.invoice_mark_sent, name="invoice_mark_sent"),
    path("invoices/<int:pk>/void/", views.invoice_void, name="invoice_void"),
    path("invoices/<int:pk>/remind/", views.invoice_send_reminder, name="invoice_send_reminder"),
    path("invoices/<int:pk>/refund/", views.invoice_refund, name="invoice_refund"),

    # Invoices (public)
    path("invoice/p/<uuid:token>/", views.invoice_public, name="invoice_public"),
    path("invoice/p/<uuid:token>/checkout/", views.invoice_checkout, name="invoice_checkout"),
    path("invoice/p/<uuid:token>/success/", views.invoice_pay_success, name="invoice_pay_success"),

    # -----------------------------
    # Payments
    # -----------------------------
    path("payments/", views.payments_list, name="payments"),
    path("invoices/<int:pk>/payments/new/", views.payment_create, name="payment_create"),

    # -----------------------------
    # Expenses
    # -----------------------------
    path("expenses/", views.expenses_list, name="expenses"),
    path("expenses/new/", views.expense_create, name="expense_create"),
    path("expenses/<int:pk>/edit/", views.expense_update, name="expense_update"),
    path("expenses/<int:pk>/delete/", views.expense_delete, name="expense_delete"),

    # -----------------------------
    # Reports
    # -----------------------------
    path("reports/", views.reports_index, name="reports"),
    path("reports/pnl/", views.report_pnl, name="report_pnl"),
    # Preferred, directory-style CSV route:
    path("reports/pnl/csv/", views.report_pnl_csv, name="report_pnl_csv"),
    # Back-compat: keep old dotted suffix (can be removed later)
    path("reports/pnl.csv", views.report_pnl_csv, name="report_pnl_csv_legacy"),

    # -----------------------------
    # Company / Team / Onboarding
    # -----------------------------
    path("company/", views.company_profile, name="company_profile"),
    path("company/edit/", views.company_edit, name="company_edit"),
    path("company/new/", views.company_create, name="company_create"),
    path("company/switch/<int:company_id>/", views.company_switch, name="company_switch"),

    path("team/", views.team_list, name="team_list"),
    path("team/invite/", views.invite_create, name="invite_create"),
    path("team/members/<int:member_id>/edit/", views.member_edit, name="member_edit"),
    path("team/members/<int:member_id>/remove/", views.member_remove, name="member_remove"),

    path("invite/<uuid:token>/", views.invite_accept, name="invite_accept"),
    path("onboarding/company/", onboarding_company, name="onboarding_company"),

    # -----------------------------
    # Estimates (private)
    # -----------------------------
    path("estimates/", views.estimates_list, name="estimates"),
    path("estimates/new/", views.estimate_create, name="estimate_create"),
    path("estimates/new/from/<int:pk>/", views.estimate_create_from, name="estimate_create_from"),
    path("estimates/<int:pk>/", views.estimate_detail, name="estimate_detail"),
    path("estimates/<int:pk>/edit/", views.estimate_update, name="estimate_update"),
    path("estimates/<int:pk>/delete/", views.estimate_delete, name="estimate_delete"),
    path("estimates/<int:pk>/mark-sent/", views.estimate_mark_sent, name="estimate_mark_sent"),
    path("estimates/<int:pk>/email/", views.estimate_email, name="estimate_email"),
    path("estimates/<int:pk>/send/", views.estimate_send_email, name="estimate_send_email"),
    path("estimates/<int:pk>/convert/", views.estimate_convert, name="estimate_convert"),
    path("estimates/<int:pk>/convert-to-project/", views.estimate_convert_to_project, name="estimate_convert_to_project"),

    # Estimates (public)
    path("estimate/p/<uuid:token>/", views.estimate_public, name="estimate_public"),
    path("estimate/p/<uuid:token>/accept/", views.estimate_public_accept, name="estimate_public_accept"),
    path("estimate/p/<uuid:token>/decline/", views.estimate_public_decline, name="estimate_public_decline"),

    # -----------------------------
    # Recurring invoices
    # -----------------------------
    path("recurring/", views.recurring_list, name="recurring_list"),
    path("recurring/new/", views.recurring_create, name="recurring_create"),
    path("recurring/<int:pk>/edit/", views.recurring_update, name="recurring_update"),
    path("recurring/<int:pk>/toggle/", views.recurring_toggle_status, name="recurring_toggle"),
    path("recurring/<int:pk>/run-now/", views.recurring_run_now, name="recurring_run_now"),
    path("recurring/<int:pk>/delete/", views.recurring_delete, name="recurring_delete"),

    # -----------------------------
    # Time / Timesheets / Approvals
    # -----------------------------
    path("time/", views.time_list, name="time_list"),
    path("timesheet/", views.timesheet_week, name="timesheet_week"),
    path("timesheet/submit/", views.timesheet_submit_week, name="timesheet_submit_week"),
    path("approvals/", views.approvals_list, name="approvals_list"),
    path("approvals/decide/", views.approvals_decide, name="approvals_decide"),

    # -----------------------------
    # Search
    # -----------------------------
    path("search/", views.search, name="search"),

    # -----------------------------
    # Notifications
    # -----------------------------
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/list/", views.notifications_list, name="notifications_list"),
    path("notifications/read/<int:pk>/", views.notification_read, name="notification_read"),
    path("notifications/read-all/", views.notifications_read_all, name="notifications_read_all"),
    path("notifications/mark-all-read/", views.notifications_mark_all_read, name="notifications_mark_all_read"),

    # -----------------------------
    # Profile
    # -----------------------------
    path("me/", views.my_profile, name="my_profile"),
    path("me/edit/", views.my_profile_edit, name="my_profile_edit"),
]
