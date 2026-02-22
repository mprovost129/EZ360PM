from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand

from django.utils import timezone

from ops.models import BackupRun, BackupRunStatus
from ops.models import BackupRestoreTest, RestoreTestOutcome


class Command(BaseCommand):
    help = "Print a restore drill checklist (and optionally record evidence)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--backup-run-id",
            type=int,
            default=0,
            help="Optional BackupRun id to reference. Defaults to latest SUCCESS run.",
        )
        parser.add_argument(
            "--record-outcome",
            choices=[RestoreTestOutcome.PASS, RestoreTestOutcome.FAIL],
            default="",
            help="Optional: record outcome immediately (pass|fail).",
        )
        parser.add_argument("--notes", default="", help="Optional notes when recording outcome.")
        parser.add_argument("--tested-by-email", default="system@ez360pm", help="Email used when recording evidence.")
        parser.add_argument(
            "--restore-window-days",
            type=int,
            default=30,
            help="Suggested cadence for restore drills (default 30).",
        )

    def handle(self, *args, **opts):
        rid = int(opts.get("backup_run_id") or 0)
        record = (opts.get("record_outcome") or "").strip()
        notes = (opts.get("notes") or "").strip()
        tested_by = (opts.get("tested_by_email") or "").strip()[:254] or "system@ez360pm"
        window_days = int(opts.get("restore_window_days") or 30)

        run = None
        if rid:
            run = BackupRun.objects.filter(pk=rid).first()
        if run is None:
            run = BackupRun.objects.filter(status=BackupRunStatus.SUCCESS).order_by("-created_at").first()

        self.stdout.write("EZ360PM Restore Drill")
        self.stdout.write("=" * 72)
        self.stdout.write(f"Suggested cadence: every {window_days} days (weekly during launch is better).")
        self.stdout.write("")

        if run is None:
            self.stdout.write("No successful BackupRun found. Run a backup first:")
            self.stdout.write("  python manage.py ez360_backup_db --gzip")
            self.stdout.write("")
        else:
            details = run.details or {}
            backup_path = (details.get("path") or "") if isinstance(details, dict) else ""
            upload = (details.get("upload") or {}) if isinstance(details, dict) else {}
            bucket = upload.get("bucket") if isinstance(upload, dict) else ""
            key = upload.get("key") if isinstance(upload, dict) else ""
            self.stdout.write(f"Reference BackupRun: id={run.id} created_at={run.created_at.isoformat()} storage={run.storage}")
            if backup_path:
                self.stdout.write(f"Local file: {backup_path}")
            if bucket and key:
                self.stdout.write(f"S3 object: s3://{bucket}/{key}")
            self.stdout.write("")

            self.stdout.write("Restore drill checklist")
            self.stdout.write("-" * 72)
            self.stdout.write("1) Create a fresh staging/throwaway Postgres database.")
            self.stdout.write("2) Restore the backup into that DB (clean/if-exists).")
            self.stdout.write("3) Run app migrations + system checks:")
            self.stdout.write("     python manage.py migrate")
            self.stdout.write("     python manage.py check")
            self.stdout.write("4) Acceptance sweep (10 minutes):")
            self.stdout.write("     - login")
            self.stdout.write("     - company switch")
            self.stdout.write("     - open invoices list")
            self.stdout.write("     - open P&L / Balance Sheet")
            self.stdout.write("     - run one Stripe webhook replay in test mode (optional)")
            self.stdout.write("5) Record PASS/FAIL in Ops (evidence).")
            self.stdout.write("")

            self.stdout.write("Evidence command")
            self.stdout.write("  python manage.py ez360_record_restore_test --outcome pass --notes \"...\" --backup-file \"...\"")
            self.stdout.write("")

        if record in {RestoreTestOutcome.PASS, RestoreTestOutcome.FAIL}:
            backup_file = ""
            if run is not None:
                d = run.details or {}
                backup_file = (d.get("path") or "") if isinstance(d, dict) else ""
                if not backup_file:
                    upload = (d.get("upload") or {}) if isinstance(d, dict) else {}
                    if isinstance(upload, dict) and upload.get("bucket") and upload.get("key"):
                        backup_file = f"s3://{upload.get('bucket')}/{upload.get('key')}"

            BackupRestoreTest.objects.create(
                tested_at=timezone.now(),
                outcome=record,
                notes=notes,
                tested_by_email=tested_by,
                details={"backup_file": backup_file} if backup_file else {},
            )
            self.stdout.write(self.style.SUCCESS(f"Recorded restore drill evidence: outcome={record}"))
