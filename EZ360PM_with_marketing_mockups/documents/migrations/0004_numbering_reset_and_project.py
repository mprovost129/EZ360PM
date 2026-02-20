from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0003_document_template_blocks"),
    ]

    operations = [
        migrations.AddField(
            model_name="numberingscheme",
            name="invoice_reset",
            field=models.CharField(
                choices=[("none", "Never"), ("monthly", "Monthly"), ("yearly", "Yearly")],
                default="none",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="numberingscheme",
            name="estimate_reset",
            field=models.CharField(
                choices=[("none", "Never"), ("monthly", "Monthly"), ("yearly", "Yearly")],
                default="none",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="numberingscheme",
            name="proposal_reset",
            field=models.CharField(
                choices=[("none", "Never"), ("monthly", "Monthly"), ("yearly", "Yearly")],
                default="none",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="numberingscheme",
            name="invoice_seq_period",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
        migrations.AddField(
            model_name="numberingscheme",
            name="estimate_seq_period",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
        migrations.AddField(
            model_name="numberingscheme",
            name="proposal_seq_period",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
        migrations.AddField(
            model_name="document",
            name="use_project_numbering",
            field=models.BooleanField(
                default=False,
                help_text="If enabled and a project is selected, the number will use PROJECTNUMBER-1, PROJECTNUMBER-2…",
            ),
        ),
        migrations.CreateModel(
            name="ProjectDocSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("doc_type", models.CharField(choices=[("invoice", "Invoice"), ("estimate", "Estimate"), ("proposal", "Proposal")], max_length=20)),
                ("next_seq", models.BigIntegerField(default=1)),
                (
                    "company",
                    models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="project_doc_sequences", to="companies.Company"),
                ),
                (
                    "project",
                    models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="doc_sequences", to="projects.project"),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("company", "project", "doc_type"),
                        name="uniq_company_project_doctype_seq",
                    )
                ]
            },
        ),
    ]
