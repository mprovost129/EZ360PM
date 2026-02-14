from django.urls import path

from . import views

app_name = "ops"

urlpatterns = [
    path("healthz/", views.healthz, name="healthz"),
    path("", views.ops_dashboard, name="dashboard"),
    path("alerts/", views.ops_alerts, name="alerts"),
    path("alerts/<int:alert_id>/resolve/", views.ops_alert_resolve, name="alert_resolve"),
    path("security/", views.ops_security, name="security"),
    path("launch-checks/", views.ops_launch_checks, name="launch_checks"),
    path("launch-gate/", views.ops_launch_gate, name="launch_gate"),
    path("reconciliation/", views.ops_reconciliation, name="reconciliation"),
    path("drift/", views.ops_drift_tools, name="drift_tools"),
    path("drift/recalc/", views.ops_drift_recalc, name="drift_recalc"),
    path("drift/link-payment/", views.ops_drift_link_payment, name="drift_link_payment"),
    path("drift/post-missing/", views.ops_drift_post_missing, name="drift_post_missing"),
    path("launch-gate/<int:item_id>/toggle/", views.ops_launch_gate_toggle, name="launch_gate_toggle"),
    path("retention/", views.ops_retention, name="retention"),
    path("retention/prune/", views.ops_retention_prune, name="retention_prune"),
    path("backups/", views.ops_backups, name="backups"),
    path("backups/record-run/", views.ops_backup_record_run, name="backup_record_run"),
    path("backups/record-restore-test/", views.ops_backup_record_restore_test, name="backup_record_restore_test"),
    path("releases/", views.ops_releases, name="releases"),
    path("companies/<int:company_id>/", views.ops_company_detail, name="company_detail"),
    path("companies/<int:company_id>/timeline/", views.ops_company_timeline, name="company_timeline"),
    path("companies/<int:company_id>/resync-subscription/", views.ops_resync_subscription, name="resync_subscription"),
]
