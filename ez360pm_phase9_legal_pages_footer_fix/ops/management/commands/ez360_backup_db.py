from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ops.models import BackupRun, BackupRunStatus
from ops.models import OpsAlertEvent, OpsAlertLevel, OpsAlertSource
from ops.services_backups import upload_backup_to_s3


def _now_stamp() -> str:
    return timezone.now().strftime("%Y%m%d_%H%M%S")


def _find_pg_dump(explicit: str | None) -> str | None:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return str(p)
        return None
    return shutil.which("pg_dump")


def _db_params() -> dict[str, Any]:
    db = settings.DATABASES.get("default", {})
    engine = db.get("ENGINE", "")
    if "postgresql" not in engine:
        raise CommandError("Default DB is not PostgreSQL; ez360_backup_db only supports Postgres.")
    return {
        "NAME": db.get("NAME") or "",
        "USER": db.get("USER") or "",
        "PASSWORD": db.get("PASSWORD") or "",
        "HOST": db.get("HOST") or "",
        "PORT": str(db.get("PORT") or ""),
    }


class Command(BaseCommand):
    help = "Create a PostgreSQL backup using pg_dump and record a BackupRun (Phase 6C/6D)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Run even if BACKUP_ENABLED is false.")
        parser.add_argument("--no-record", action="store_true", help="Do not record BackupRun rows.")
        parser.add_argument("--pg-dump-path", default="", help="Optional explicit path to pg_dump.")
        parser.add_argument("--gzip", action="store_true", help="Gzip the output (recommended).")
        parser.add_argument("--notes", default="", help="Optional notes stored with the BackupRun.")
        parser.add_argument("--storage", default="", help="Override BACKUP_STORAGE for the recorded run.")
        parser.add_argument("--output-dir", default="", help="Override EZ360_BACKUP_DIR for this run.")
        parser.add_argument("--filename", default="", help="Optional filename (without dir). Defaults to timestamped name.")

    def handle(self, *args, **options):
        backup_enabled = bool(getattr(settings, "BACKUP_ENABLED", False))
        if not backup_enabled and not options["force"]:
            raise CommandError("BACKUP_ENABLED is false. Set BACKUP_ENABLED=1 (or use --force) to run a backup.")

        output_dir = Path(options["output_dir"] or getattr(settings, "EZ360_BACKUP_DIR", Path(settings.BASE_DIR / "backups")))
        output_dir.mkdir(parents=True, exist_ok=True)

        gzip_enabled = bool(options["gzip"])
        stamp = _now_stamp()
        base_name = options["filename"] or f"ez360pm_db_{stamp}.sql"
        out_path = output_dir / base_name
        final_path = out_path.with_suffix(out_path.suffix + ".gz") if gzip_enabled else out_path

        pg_dump_path = _find_pg_dump(options["pg_dump_path"] or getattr(settings, "EZ360_PG_DUMP_PATH", "").strip() or None)
        if not pg_dump_path:
            raise CommandError("pg_dump not found. Install PostgreSQL client tools or set EZ360_PG_DUMP_PATH.")

        params = _db_params()

        env = os.environ.copy()
        if params["PASSWORD"]:
            env["PGPASSWORD"] = params["PASSWORD"]

        cmd = [
            pg_dump_path,
            "--no-owner",
            "--no-privileges",
            "--format=plain",
            "--encoding=UTF8",
        ]
        if params["HOST"]:
            cmd += ["--host", params["HOST"]]
        if params["PORT"]:
            cmd += ["--port", params["PORT"]]
        if params["USER"]:
            cmd += ["--username", params["USER"]]
        cmd += [params["NAME"]]

        start = time.time()
        run_row = None
        record = not options["no_record"]
        storage = (options["storage"] or getattr(settings, "BACKUP_STORAGE", "host_managed")).strip()

        try:
            if gzip_enabled:
                with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env) as proc:
                    assert proc.stdout is not None
                    with gzip.open(final_path, "wb") as gz:
                        shutil.copyfileobj(proc.stdout, gz)
                    stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
                    rc = proc.wait()
                    if rc != 0:
                        raise CommandError(f"pg_dump failed (rc={rc}): {stderr[:800]}")
            else:
                completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
                if completed.returncode != 0:
                    raise CommandError(f"pg_dump failed (rc={completed.returncode}): {completed.stderr.decode('utf-8', errors='replace')[:800]}")
                final_path.write_bytes(completed.stdout)

            elapsed_ms = int((time.time() - start) * 1000)
            size_bytes = final_path.stat().st_size if final_path.exists() else 0

            upload_meta = None
            if storage.lower() == "s3":
                # Upload to S3 and record metadata (bucket/key/sha256).
                upload_meta = upload_backup_to_s3(final_path)

            if record:
                run_row = BackupRun.objects.create(
                    status=BackupRunStatus.SUCCESS,
                    storage=storage,
                    size_bytes=size_bytes,
                    notes=options["notes"] or "",
                    initiated_by_email="",
                    details={
                        "elapsed_ms": elapsed_ms,
                        "path": str(final_path),
                        "gzip": gzip_enabled,
                        "db_name": params["NAME"],
                        "upload": upload_meta or {},
                    },
                )

            self.stdout.write(self.style.SUCCESS(f"Backup created: {final_path} ({size_bytes} bytes, {elapsed_ms} ms)"))
            if run_row:
                self.stdout.write(self.style.SUCCESS(f"Recorded BackupRun id={run_row.id}"))
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            if record:
                BackupRun.objects.create(
                    status=BackupRunStatus.FAILED,
                    storage=storage,
                    size_bytes=0,
                    notes=options["notes"] or "",
                    initiated_by_email="",
                    details={
                        "elapsed_ms": elapsed_ms,
                        "error": str(e)[:1000],
                        "gzip": gzip_enabled,
                        "db_name": params.get("NAME", ""),
                    },
                )

                # Raise a staff-visible alert (best-effort).
                try:
                    OpsAlertEvent.objects.create(
                        level=OpsAlertLevel.ERROR,
                        source=OpsAlertSource.BACKUP,
                        company=None,
                        title="Database backup FAILED",
                        message=str(e)[:500],
                        details={"cmd": "ez360_backup_db", "elapsed_ms": elapsed_ms},
                    )
                except Exception:
                    pass
            raise
