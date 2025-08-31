# core/migrations/00xx_estimate_public_token.py
from __future__ import annotations
import uuid
from django.db import migrations, models

def backfill_tokens(apps, schema_editor):
    Estimate = apps.get_model("core", "Estimate")
    for est in Estimate.objects.filter(public_token__isnull=True):
        est.public_token = uuid.uuid4()
        est.save(update_fields=["public_token"])

class Migration(migrations.Migration):
    # if this replaces your previous attempt, keep its same filename/order
    dependencies = [
        ("core", "0018_remove_notification_core_notifi_recipie_43dea6_idx_and_more"),  # replace with your real previous migration
    ]

    # we’ll run one statement outside a transaction for safety with DO $$ ... $$
    atomic = True

    operations = [
        # 1) Make sure the column exists (no-op if it already does)
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE core_estimate ADD COLUMN IF NOT EXISTS public_token uuid",
                    reverse_sql="ALTER TABLE core_estimate DROP COLUMN IF EXISTS public_token",
                ),
            ],
            state_operations=[
                # Update Django’s state to include the field
                migrations.AddField(
                    model_name="estimate",
                    name="public_token",
                    field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
                ),
            ],
        ),
        # 2) Fill any NULLs
        migrations.RunPython(backfill_tokens, migrations.RunPython.noop),

        # 3) Enforce NOT NULL (safe if already set)
        migrations.RunSQL(
            sql="ALTER TABLE core_estimate ALTER COLUMN public_token SET NOT NULL",
            reverse_sql="ALTER TABLE core_estimate ALTER COLUMN public_token DROP NOT NULL",
        ),

        # 4) Enforce UNIQUE (safely, only if it doesn’t already exist)
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM   pg_constraint
                    WHERE  conrelid = 'core_estimate'::regclass
                    AND    conname  = 'core_estimate_public_token_key'
                ) THEN
                    ALTER TABLE core_estimate
                    ADD CONSTRAINT core_estimate_public_token_key UNIQUE (public_token);
                END IF;
            END$$;
            """,
            reverse_sql="ALTER TABLE core_estimate DROP CONSTRAINT IF EXISTS core_estimate_public_token_key",
        ),
    ]
