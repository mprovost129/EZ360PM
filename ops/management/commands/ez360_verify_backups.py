from __future__ import annotations

import gzip
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from ops.models import BackupRun, BackupRunStatus
from ops.models import OpsAlertEvent, OpsAlertLevel, OpsAlertSource


class Command(BaseCommand):
    help = "Verify backups are recent and readable; create an Ops alert on failure (Pack 22)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-age-hours",
            type=int,
            default=int(getattr(settings, "BACKUP_VERIFY_MAX_AGE_HOURS", 26) or 26),
            help="Max allowed age of the most recent SUCCESS backup (default from settings: BACKUP_VERIFY_MAX_AGE_HOURS, fallback 26).",
        )
        parser.add_argument(
            "--min-size-bytes",
            type=int,
            default=int(getattr(settings, "BACKUP_VERIFY_MIN_SIZE_BYTES", 1024) or 1024),
            help="Minimum expected size of backup file (default from settings: BACKUP_VERIFY_MIN_SIZE_BYTES, fallback 1024).",
        )
        parser.add_argument(
            "--create-alert",
            action="store_true",
            default=True,
            help="If verification fails, create an OpsAlertEvent (default: enabled).",
        )

    def _fail(self, message: str, *, details: dict | None = None, create_alert: bool = True) -> None:
        msg = (message or "Backup verification failed").strip()
        self.stdout.write(self.style.ERROR("FAILED: " + msg))
        if create_alert:
            try:
                OpsAlertEvent.objects.create(
                    level=OpsAlertLevel.ERROR,
                    source=OpsAlertSource.BACKUP,
                    company=None,
                    title="Backup verification FAILED",
                    message=msg[:500],
                    details=details or {},
                )
            except Exception:
                pass
        raise SystemExit(2)

    def handle(self, *args, **opts):
        max_age_hours = int(opts.get("max_age_hours") or 26)
        min_size = int(opts.get("min_size_bytes") or 1024)
        create_alert = bool(opts.get("create_alert", True))

        now = timezone.now()
        cutoff = now - timedelta(hours=max(1, max_age_hours))

        latest = BackupRun.objects.filter(status=BackupRunStatus.SUCCESS).order_by("-created_at").first()
        if latest is None:
            self._fail("No successful backups recorded.", details={"reason": "no_success_rows"}, create_alert=create_alert)

        age_ok = latest.created_at >= cutoff
        size_ok = int(latest.size_bytes or 0) >= max(0, min_size)

        # Integrity check (best-effort)
        integrity_ok = True
        integrity_note = ""
        storage = (latest.storage or getattr(settings, "BACKUP_STORAGE", "") or "").strip().lower() or "host_managed"
        details = latest.details or {}

        if storage == "s3":
            upload = (details.get("upload") or {}) if isinstance(details, dict) else {}
            bucket = (upload.get("bucket") or getattr(settings, "BACKUP_S3_BUCKET", "") or "").strip()
            key = (upload.get("key") or "").strip()
            if not bucket or not key:
                integrity_ok = False
                integrity_note = "Missing S3 upload metadata (bucket/key)."
            else:
                try:
                    import boto3  # type: ignore

                    s3 = boto3.client("s3")
                    head = s3.head_object(Bucket=bucket, Key=key)
                    remote_size = int(head.get("ContentLength") or 0)
                    if remote_size <= 0:
                        integrity_ok = False
                        integrity_note = "S3 object exists but size is 0."
                    elif int(latest.size_bytes or 0) and remote_size != int(latest.size_bytes or 0):
                        integrity_ok = False
                        integrity_note = f"S3 size mismatch (db={int(latest.size_bytes or 0)} vs s3={remote_size})."
                    else:
                        integrity_note = f"S3 ok ({bucket}/{key}, {remote_size} bytes)."
                except Exception as e:
                    integrity_ok = False
                    integrity_note = f"S3 head_object failed: {e!r}"[:240]
        else:
            # Local path integrity check (only if the recorded path exists)
            path = (details.get("path") or "") if isinstance(details, dict) else ""
            if path:
                p = Path(str(path))
                if not p.exists() or not p.is_file():
                    integrity_ok = False
                    integrity_note = f"Backup file not found on disk: {p}"
                else:
                    try:
                        # For gzip backups, try reading a small chunk.
                        if str(p).endswith(".gz"):
                            with gzip.open(p, "rb") as f:
                                _ = f.read(64)
                        else:
                            with p.open("rb") as f:
                                _ = f.read(64)
                        integrity_note = f"Local file ok ({p.name})."
                    except Exception as e:
                        integrity_ok = False
                        integrity_note = f"Local file read failed: {e!r}"[:240]
            else:
                # We can't validate file readability without a recorded path.
                integrity_note = "No local file path recorded; skipping file readability check."

        ok = bool(age_ok and size_ok and integrity_ok)

        self.stdout.write("Backup verification")
        self.stdout.write(f"- Latest SUCCESS: {latest.created_at.isoformat()} (id={latest.id})")
        self.stdout.write(f"- Storage: {storage}")
        self.stdout.write(f"- Age OK: {age_ok} (cutoff={cutoff.isoformat()})")
        self.stdout.write(f"- Size OK: {size_ok} (size_bytes={int(latest.size_bytes or 0)}, min={min_size})")
        self.stdout.write(f"- Integrity: {integrity_ok} ({integrity_note})")

        if not ok:
            self._fail(
                "Backup verification failed (stale/missing/invalid).",
                details={
                    "latest_backup_run_id": latest.id,
                    "latest_created_at": latest.created_at.isoformat(),
                    "storage": storage,
                    "age_ok": age_ok,
                    "size_ok": size_ok,
                    "integrity_ok": integrity_ok,
                    "integrity_note": integrity_note,
                },
                create_alert=create_alert,
            )

        self.stdout.write(self.style.SUCCESS("OK: backups are recent and passed integrity checks."))
