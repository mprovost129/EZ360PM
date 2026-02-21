from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ops.models import BackupRestoreTest, RestoreTestOutcome, OpsAlertEvent, OpsAlertLevel, OpsAlertSource


class Command(BaseCommand):
    help = "Record a backup restore test result in Ops (evidence for launch readiness)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--outcome",
            choices=[RestoreTestOutcome.PASS, RestoreTestOutcome.FAIL],
            default=RestoreTestOutcome.PASS,
            help="Restore test outcome: pass|fail (default: pass).",
        )
        parser.add_argument("--notes", default="", help="Human notes about the restore test.")
        parser.add_argument(
            "--tested-by-email",
            default="",
            help="Optional email of the person who performed the restore test.",
        )
        parser.add_argument(
            "--backup-file",
            default="",
            help="Optional path or identifier of the backup file used for the restore test.",
        )
        parser.add_argument(
            "--details-json",
            default="",
            help="Optional JSON dict string for extra details (e.g., host, duration, db name).",
        )
        parser.add_argument(
            "--create-alert-on-fail",
            action="store_true",
            default=True,
            help="If outcome=fail, create an OpsAlertEvent (default: enabled).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        outcome: str = options["outcome"]
        notes: str = (options.get("notes") or "").strip()
        tested_by_email: str = (options.get("tested_by_email") or "").strip()
        backup_file: str = (options.get("backup_file") or "").strip()
        details_json: str = (options.get("details_json") or "").strip()
        create_alert_on_fail: bool = bool(options.get("create_alert_on_fail", True))

        details: dict[str, Any] = {}
        if backup_file:
            details["backup_file"] = backup_file

        if details_json:
            try:
                extra = json.loads(details_json)
                if not isinstance(extra, dict):
                    raise ValueError("details-json must be a JSON object")
                details.update(extra)
            except Exception as e:
                raise CommandError(f"Invalid --details-json: {e}") from e

        rt = BackupRestoreTest.objects.create(
            tested_at=timezone.now(),
            outcome=outcome,
            notes=notes,
            tested_by_email=tested_by_email,
            details=details,
        )

        if outcome == RestoreTestOutcome.FAIL and create_alert_on_fail:
            OpsAlertEvent.objects.create(
                level=OpsAlertLevel.ERROR,
                source=OpsAlertSource.RESTORE_TEST,
                company=None,
                title="Backup restore test FAILED",
                message=notes or "A restore test was recorded as FAIL. Review details and re-test.",
                details={"restore_test_id": rt.id, **details},
            )

        self.stdout.write(self.style.SUCCESS(f"Recorded restore test: id={rt.id} outcome={rt.outcome}"))
