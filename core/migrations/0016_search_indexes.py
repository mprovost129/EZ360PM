from django.db import migrations
from django.contrib.postgres.indexes import GinIndex

class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_enable_pg_extensions"),  # <-- update to match your prior migration name/number
    ]

    # CREATE the FTS indexes via SQL (works across Django versions),
    # and add trigram indexes using GinIndex(fields=..., opclasses=...).
    operations = [
        # --- Full-text indexes (GIN over to_tsvector) ---
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS client_fts_gin "
                "ON core_client USING GIN (to_tsvector('english', "
                "COALESCE(org,'') || ' ' || COALESCE(first_name,'') || ' ' || COALESCE(last_name,'') || ' ' || COALESCE(email,'')));"
            ),
            reverse_sql="DROP INDEX IF EXISTS client_fts_gin;"
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS project_fts_gin "
                "ON core_project USING GIN (to_tsvector('english', "
                "COALESCE(name,'') || ' ' || COALESCE(number,'')));"
            ),
            reverse_sql="DROP INDEX IF EXISTS project_fts_gin;"
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS invoice_fts_gin "
                "ON core_invoice USING GIN (to_tsvector('english', COALESCE(number,'')));"
            ),
            reverse_sql="DROP INDEX IF EXISTS invoice_fts_gin;"
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS estimate_fts_gin "
                "ON core_estimate USING GIN (to_tsvector('english', COALESCE(number,'')));"
            ),
            reverse_sql="DROP INDEX IF EXISTS estimate_fts_gin;"
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS expense_fts_gin "
                "ON core_expense USING GIN (to_tsvector('english', "
                "COALESCE(description,'') || ' ' || COALESCE(vendor,'') || ' ' || COALESCE(category,'')));"
            ),
            reverse_sql="DROP INDEX IF EXISTS expense_fts_gin;"
        ),

        # --- Trigram (pg_trgm) indexes for fuzzy matches ---
        migrations.AddIndex(
            model_name="client",
            index=GinIndex(name="client_org_trgm", fields=["org"], opclasses=["gin_trgm_ops"]),
        ),
        migrations.AddIndex(
            model_name="client",
            index=GinIndex(name="client_email_trgm", fields=["email"], opclasses=["gin_trgm_ops"]),
        ),
        migrations.AddIndex(
            model_name="project",
            index=GinIndex(name="project_name_trgm", fields=["name"], opclasses=["gin_trgm_ops"]),
        ),
        migrations.AddIndex(
            model_name="project",
            index=GinIndex(name="project_number_trgm", fields=["number"], opclasses=["gin_trgm_ops"]),
        ),
        migrations.AddIndex(
            model_name="invoice",
            index=GinIndex(name="invoice_number_trgm", fields=["number"], opclasses=["gin_trgm_ops"]),
        ),
        migrations.AddIndex(
            model_name="estimate",
            index=GinIndex(name="estimate_number_trgm", fields=["number"], opclasses=["gin_trgm_ops"]),
        ),
        migrations.AddIndex(
            model_name="expense",
            index=GinIndex(name="expense_desc_trgm", fields=["description"], opclasses=["gin_trgm_ops"]),
        ),
    ]