from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


DEFAULT_ITEMS = [
    {
        "key": "2fa_verified_prod",
        "title": "2FA + login throttling verified in production",
        "description": "Confirm owner/admin 2FA enforcement and lockout/throttle behavior in production.",
    },
    {
        "key": "invoice_immutability_validated",
        "title": "Invoice immutability + reconciliation validated",
        "description": "Verify invoices cannot be edited after Sent/Paid; validate reconciliation view matches payments and credits.",
    },
    {
        "key": "backup_restore_tested",
        "title": "Backup restore test completed successfully",
        "description": "Run and document a restore test in staging/production per backup SOP.",
    },
    {
        "key": "monitoring_alerts_tested",
        "title": "Monitoring alerts tested (Sentry + Ops Alerts)",
        "description": "Trigger a controlled exception and a controlled alert path; confirm visibility and routing.",
    },
    {
        "key": "e2e_flow_tested",
        "title": "End-to-end flow tested",
        "description": "Client → Project → Time → Invoice → Payment → Reports (P&L, Aging).",
    },
]


def seed_launch_gate_items(apps, schema_editor):
    LaunchGateItem = apps.get_model("ops", "LaunchGateItem")
    for item in DEFAULT_ITEMS:
        LaunchGateItem.objects.get_or_create(
            key=item["key"],
            defaults={
                "title": item["title"],
                "description": item.get("description", ""),
                "is_complete": False,
                "created_at": timezone.now(),
                "updated_at": timezone.now(),
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("ops", "0002_rename_ops_opsaler_source_4d1b6e_idx_ops_opsaler_source_5b6301_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="LaunchGateItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=64, unique=True)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("is_complete", models.BooleanField(db_index=True, default=False)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(db_index=True, default=timezone.now)),
                ("updated_at", models.DateTimeField(default=timezone.now)),
                ("completed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="completed_launch_gate_items", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["key"],
            },
        ),
        migrations.RunPython(seed_launch_gate_items, migrations.RunPython.noop),
    ]
