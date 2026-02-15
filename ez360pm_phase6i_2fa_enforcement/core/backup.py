from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Tuple

from django.conf import settings


@dataclass(frozen=True)
class BackupResult:
    kind: str  # "db" | "media"
    path: Path
    size_bytes: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _timestamp_slug() -> str:
    return _utcnow().strftime("%Y%m%d_%H%M%S_utc")


def _db_conn_from_django_settings() -> Tuple[str, str, str, str, str]:
    """
    Returns (name, user, password, host, port) from settings.DATABASES.
    """
    db = settings.DATABASES.get("default", {})
    return (
        str(db.get("NAME", "")),
        str(db.get("USER", "")),
        str(db.get("PASSWORD", "")),
        str(db.get("HOST", "")),
        str(db.get("PORT", "")),
    )


def _find_pg_dump() -> str | None:
    return shutil.which("pg_dump")


def _find_pg_restore() -> str | None:
    return shutil.which("pg_restore")


def create_postgres_dump(
    *,
    out_dir: Path,
    prefix: str = "ez360pm",
    format_custom: bool = True,
) -> BackupResult:
    """
    Create a PostgreSQL backup using pg_dump.

    - Uses a custom-format dump (-Fc) by default. This is compressed and best for pg_restore.
    - Requires `pg_dump` to be available in PATH on the host.
    """
    pg_dump = _find_pg_dump()
    if not pg_dump:
        raise RuntimeError(
            "pg_dump not found on PATH. Install PostgreSQL client tools on the server "
            "or use a managed backup mechanism. See docs/BACKUP_RECOVERY.md."
        )

    name, user, password, host, port = _db_conn_from_django_settings()
    if not all([name, user, host, port]):
        raise RuntimeError(
            "Database settings are incomplete (NAME/USER/HOST/PORT). "
            "Set POSTGRES_* env vars (recommended) and try again."
        )

    _ensure_dir(out_dir)

    ts = _timestamp_slug()
    ext = "dump" if format_custom else "sql"
    out_path = out_dir / f"{prefix}_db_{ts}.{ext}"

    cmd: List[str] = [pg_dump]
    if format_custom:
        cmd += ["-Fc"]
    cmd += [
        "-h",
        host,
        "-p",
        str(port),
        "-U",
        user,
        "-f",
        str(out_path),
        name,
    ]

    env = os.environ.copy()
    if password:
        env["PGPASSWORD"] = password

    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "pg_dump failed.\n"
            f"STDOUT: {proc.stdout.strip()}\n"
            f"STDERR: {proc.stderr.strip()}"
        )

    size = out_path.stat().st_size if out_path.exists() else 0
    return BackupResult(kind="db", path=out_path, size_bytes=size)


def create_media_backup(*, out_dir: Path, prefix: str = "ez360pm") -> BackupResult:
    """
    Create a .tar.gz of MEDIA_ROOT.

    NOTE: This is primarily for single-server setups. For production, prefer object storage (S3) and
    rely on bucket versioning + lifecycle rules rather than tarballing media.
    """
    media_root = getattr(settings, "MEDIA_ROOT", "") or ""
    if not media_root:
        raise RuntimeError("MEDIA_ROOT is not configured; cannot back up media.")
    media_path = Path(media_root)
    if not media_path.exists():
        raise RuntimeError(f"MEDIA_ROOT path not found: {media_path}")

    _ensure_dir(out_dir)
    ts = _timestamp_slug()
    out_base = out_dir / f"{prefix}_media_{ts}"
    archive_path = Path(shutil.make_archive(str(out_base), "gztar", root_dir=str(media_path)))

    size = archive_path.stat().st_size if archive_path.exists() else 0
    return BackupResult(kind="media", path=archive_path, size_bytes=size)


def prune_backups(
    *,
    backup_dir: Path,
    keep_last: int,
    max_age_days: int,
    prefixes: Iterable[str] = ("ez360pm_db_", "ez360pm_media_"),
) -> int:
    """
    Prune backup files in backup_dir.

    Rules:
    - Always keep the newest `keep_last` files per prefix (sorted by mtime).
    - Also delete any files older than `max_age_days`, unless within kept set.
    """
    if keep_last < 0:
        keep_last = 0
    if max_age_days < 0:
        max_age_days = 0

    now = _utcnow()
    cutoff = now - timedelta(days=max_age_days)

    deleted = 0
    for prefix in prefixes:
        files = [p for p in backup_dir.glob(f"{prefix}*") if p.is_file()]
        files_sorted = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
        keep_set = set(files_sorted[:keep_last])

        for p in files_sorted[keep_last:]:
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            except Exception:
                mtime = now

            if p in keep_set:
                continue

            if mtime < cutoff:
                try:
                    p.unlink()
                    deleted += 1
                except Exception:
                    pass

    return deleted


def restore_postgres_dump(*, dump_path: Path, drop_existing: bool = False) -> None:
    """
    Restore a PostgreSQL custom-format dump. Requires `pg_restore`.

    This function is NOT wired to a management command by default to reduce accidental misuse.
    Use docs/BACKUP_RECOVERY.md for the safe, explicit restore procedure.
    """
    pg_restore = _find_pg_restore()
    if not pg_restore:
        raise RuntimeError("pg_restore not found on PATH.")
    if not dump_path.exists():
        raise RuntimeError(f"Dump file not found: {dump_path}")

    name, user, password, host, port = _db_conn_from_django_settings()
    if not all([name, user, host, port]):
        raise RuntimeError("Database settings are incomplete (NAME/USER/HOST/PORT).")

    cmd: List[str] = [
        pg_restore,
        "-h",
        host,
        "-p",
        str(port),
        "-U",
        user,
        "-d",
        name,
    ]
    if drop_existing:
        cmd += ["--clean", "--if-exists"]

    cmd += [str(dump_path)]

    env = os.environ.copy()
    if password:
        env["PGPASSWORD"] = password

    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "pg_restore failed.\n"
            f"STDOUT: {proc.stdout.strip()}\n"
            f"STDERR: {proc.stderr.strip()}"
        )
