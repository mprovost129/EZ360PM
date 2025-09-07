# payments/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("payments/", views.payments_list, name="payments"),
    path("invoices/<int:pk>/payments/new/", views.payment_create, name="payment_create"),
]