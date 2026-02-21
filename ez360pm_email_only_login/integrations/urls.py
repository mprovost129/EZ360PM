from django.urls import path

from . import views

app_name = "integrations"

urlpatterns = [
    path("integrations/dropbox/", views.dropbox_settings, name="dropbox_settings"),
    path("integrations/dropbox/connect/", views.dropbox_connect, name="dropbox_connect"),
    path("integrations/dropbox/callback/", views.dropbox_callback, name="dropbox_callback"),
    path("integrations/dropbox/disconnect/", views.dropbox_disconnect, name="dropbox_disconnect"),

    path("integrations/banking/", views.banking_settings, name="banking_settings"),
    path("integrations/banking/connect/", views.banking_connect, name="banking_connect"),
    path("integrations/banking/link-token/", views.banking_link_token, name="banking_link_token"),
    path("integrations/banking/exchange/", views.banking_exchange, name="banking_exchange"),
    path("integrations/banking/sync/", views.banking_sync, name="banking_sync"),
    path("integrations/banking/apply-rules/", views.banking_apply_rules, name="banking_apply_rules"),
    path("integrations/banking/review/", views.banking_review_queue, name="banking_review_queue"),
    path("integrations/banking/review/bulk/", views.banking_review_bulk_action, name="banking_review_bulk_action"),

    # Legacy summary (kept)
    path("integrations/banking/reconcile/", views.banking_reconcile, name="banking_reconcile"),

    # Phase 9: lockable reconciliation periods
    path(
        "integrations/banking/reconciliation/",
        views.banking_reconciliation_periods,
        name="banking_reconciliation_periods",
    ),
    path(
        "integrations/banking/reconciliation/new/",
        views.banking_reconciliation_new,
        name="banking_reconciliation_new",
    ),
    path(
        "integrations/banking/reconciliation/<int:pk>/",
        views.banking_reconciliation_detail,
        name="banking_reconciliation_detail",
    ),
    path(
        "integrations/banking/reconciliation/<int:pk>/lock/",
        views.banking_reconciliation_lock,
        name="banking_reconciliation_lock",
    ),
    path(
        "integrations/banking/reconciliation/<int:pk>/unlock/",
        views.banking_reconciliation_unlock,
        name="banking_reconciliation_unlock",
    ),
    path(
        "integrations/banking/reconciliation/<int:pk>/export.csv",
        views.banking_reconciliation_export_csv,
        name="banking_reconciliation_export_csv",
    ),

    path(
        "integrations/banking/tx/<int:tx_id>/create-expense/",
        views.banking_tx_create_expense,
        name="banking_tx_create_expense",
    ),
    path(
        "integrations/banking/tx/<int:tx_id>/link-existing/",
        views.banking_tx_link_existing,
        name="banking_tx_link_existing",
    ),
    path("integrations/banking/tx/<int:tx_id>/mark/<str:status>/", views.banking_tx_mark, name="banking_tx_mark"),

    path("integrations/banking/rules/", views.banking_rules, name="banking_rules"),
    path("integrations/banking/rules/new/", views.banking_rule_create, name="banking_rule_create"),
    path("integrations/banking/rules/<int:rule_id>/edit/", views.banking_rule_edit, name="banking_rule_edit"),
    path("integrations/banking/rules/<int:rule_id>/delete/", views.banking_rule_delete, name="banking_rule_delete"),
    path("integrations/banking/disconnect/", views.banking_disconnect, name="banking_disconnect"),
]
