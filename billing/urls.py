# billing/urls.py
from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    # Customer-facing
    path("plans/", views.plans, name="plans"),
    path("subscribe/<slug:slug>/", views.subscribe, name="subscribe"),
    path("portal/", views.portal, name="portal"),

    # Stripe webhook
    path("webhook/stripe/", views.webhook_stripe, name="stripe_webhook"),

    # Admin/staff
    path("webhooks/logs/", views.webhook_logs, name="webhook_logs"),
]
