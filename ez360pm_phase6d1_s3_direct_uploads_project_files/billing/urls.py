from django.urls import path

from . import views


app_name = "billing"


urlpatterns = [
    path("billing/", views.billing_overview, name="overview"),
    path("billing/set-plan/", views.set_plan, name="set_plan"),
    path("billing/mark-active/", views.mark_active, name="mark_active"),
    path("billing/start-checkout/", views.start_checkout, name="start_checkout"),
    path("billing/portal/", views.portal, name="portal"),
    path("billing/webhook-history/", views.webhook_history, name="webhook_history"),
    path("billing/webhook-history/<int:pk>/", views.webhook_event_detail, name="webhook_event_detail"),
    path("billing/webhook/stripe/", __import__("billing.webhooks", fromlist=["stripe_webhook"]).stripe_webhook, name="stripe_webhook"),
    path("billing/locked/", views.locked, name="locked"),
]