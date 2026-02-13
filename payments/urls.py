from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("payments/", views.payment_list, name="payment_list"),
    path("payments/new/", views.payment_create, name="payment_create"),
    path("payments/<uuid:pk>/edit/", views.payment_edit, name="payment_edit"),
    path("payments/<uuid:pk>/refund/", views.payment_refund, name="payment_refund"),
    path("payments/<uuid:pk>/delete/", views.payment_delete, name="payment_delete"),
    path("credits/", views.credit_summary, name="credit_summary"),
]
