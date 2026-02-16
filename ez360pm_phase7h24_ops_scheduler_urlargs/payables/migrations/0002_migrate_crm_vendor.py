from __future__ import annotations

from django.db import migrations


def copy_crm_vendors_to_payables(apps, schema_editor):
    # Copy existing crm.Vendor rows into payables.Vendor, preserving UUID PKs so
    # downstream FKs (eg. expenses.Expense.vendor) remain valid after we repoint.
    try:
        CrmVendor = apps.get_model("crm", "Vendor")
    except LookupError:
        return  # already removed / not present

    PayablesVendor = apps.get_model("payables", "Vendor")

    for v in CrmVendor.objects.all():
        PayablesVendor.objects.get_or_create(
            id=v.id,
            defaults={
                "company_id": v.company_id,
                "name": v.name,
                "email": getattr(v, "email", "") or "",
                "phone": getattr(v, "phone", "") or "",
                "notes": getattr(v, "notes", "") or "",
                "is_active": True,
                # carry soft-delete + sync metadata if present on SyncModel
                "created_at": getattr(v, "created_at", None),
                "updated_at": getattr(v, "updated_at", None),
                "deleted_at": getattr(v, "deleted_at", None),
                "created_by_user_id": getattr(v, "created_by_user_id", None),
                "updated_by_user_id": getattr(v, "updated_by_user_id", None),
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("payables", "0001_initial"),
        ("crm", "0002_client_company_email_index"),
    ]

    operations = [
        migrations.RunPython(copy_crm_vendors_to_payables, migrations.RunPython.noop),
    ]
