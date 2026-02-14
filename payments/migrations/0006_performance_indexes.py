from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0005_rename_payments_ref_company_payment_created_idx_payments_pa_company_358cef_idx_and_more"),
    ]

    operations = [
        # Payment indexes
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["company", "status", "payment_date"], name="payments_pa_company_status_date_idx"),
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["company", "invoice"], name="payments_pa_company_invoice_idx"),
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["company", "client"], name="payments_pa_company_client_idx"),
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["company", "stripe_payment_intent_id"], name="payments_pa_company_pi_idx"),
        ),

        # ClientCreditLedgerEntry indexes
        migrations.AddIndex(
            model_name="clientcreditledgerentry",
            index=models.Index(fields=["company", "client", "created_at"], name="payments_ccle_company_client_created_idx"),
        ),
        migrations.AddIndex(
            model_name="clientcreditledgerentry",
            index=models.Index(fields=["company", "invoice"], name="payments_ccle_company_invoice_idx"),
        ),

        # ClientCreditApplication indexes (Meta indexes were previously mis-declared)
        migrations.AddIndex(
            model_name="clientcreditapplication",
            index=models.Index(fields=["company", "client", "applied_at"], name="payments_cca_company_client_applied_idx"),
        ),
        migrations.AddIndex(
            model_name="clientcreditapplication",
            index=models.Index(fields=["company", "invoice"], name="payments_cca_company_invoice_idx"),
        ),
    ]
