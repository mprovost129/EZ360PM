from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("payments/", views.payment_list, name="payment_list"),
    path("payments/new/", views.payment_create, name="payment_create"),
    path("payments/<uuid:pk>/edit/", views.payment_edit, name="payment_edit"),
    path("payments/<uuid:pk>/refund/", views.payment_refund, name="payment_refund"),
    path("payments/<uuid:pk>/delete/", views.payment_delete, name="payment_delete"),
    path("invoices/<uuid:invoice_id>/reconcile/", views.invoice_reconcile, name="invoice_reconcile"),
    path("credits/", views.credit_summary, name="credit_summary"),

    # Stripe Connect payouts
    path("get-paid/", views.get_paid, name="get_paid"),
    path("get-paid/start/", views.get_paid_start, name="get_paid_start"),
    path("get-paid/return/", views.get_paid_return, name="get_paid_return"),
]
