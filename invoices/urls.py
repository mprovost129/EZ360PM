# invoices/urls.py
from django.urls import path

from . import views

app_name = "invoices"

urlpatterns = [

    # -----------------------------
    # Invoices (private)
    # -----------------------------
    path("invoices/", views.invoices, name="invoices"),
    path("invoices/new/", views.invoice_create, name="invoice_create"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("invoices/<int:pk>/edit/", views.invoice_update, name="invoice_update"),
    path("invoices/<int:pk>/delete/", views.invoice_delete, name="invoice_delete"),
    path("invoices/<int:pk>/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("invoices/<int:pk>/email/", views.invoice_email, name="invoice_email"),
    path("invoices/<int:pk>/mark-sent/", views.invoice_mark_sent, name="invoice_mark_sent"),
    path("invoices/<int:pk>/remind/", views.invoice_send_reminder, name="invoice_send_reminder"),
    path("invoices/<int:pk>/refund/", views.invoice_refund, name="invoice_refund"),
    path("projects/<int:pk>/invoice-time/", views.project_invoice_time, name="project_invoice_time"),

    # Invoices (public)
    path("invoice/p/<uuid:token>/", views.invoice_public, name="invoice_public"),
    path("invoice/p/<uuid:token>/checkout/", views.invoice_checkout, name="invoice_checkout"),
    path("invoice/p/<uuid:token>/success/", views.invoice_pay_success, name="invoice_pay_success"),
    
    # -----------------------------
    # Recurring invoices
    # -----------------------------
    path("recurring/", views.recurring_list, name="recurring_list"),
    path("recurring/new/", views.recurring_create, name="recurring_create"),
    path("recurring/<int:pk>/edit/", views.recurring_update, name="recurring_update"),
    path("recurring/<int:pk>/toggle/", views.recurring_toggle_status, name="recurring_toggle"),
    path("recurring/<int:pk>/run-now/", views.recurring_run_now, name="recurring_run_now"),
    path("recurring/<int:pk>/delete/", views.recurring_delete, name="recurring_delete"),
]