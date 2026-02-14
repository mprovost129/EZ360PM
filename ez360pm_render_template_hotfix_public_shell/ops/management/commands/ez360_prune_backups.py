from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.core.management.base import BaseCommand

_BACKUP_RE = re.compile(r"^ez360pm_db_(\d{8}_\d{6})\.sql(\.gz)?$")


@dataclass(frozen=True)
class BackupFile:
    path: Path
    mtime: float


def _backup_dir() -> Path:
    p = Path(getattr(settings, "EZ360_BACKUP_DIR", "") or "")
    if not p:
        # Fall back to BASE_DIR/backups
        base = Path(getattr(settings, "BASE_DIR"))
        p = base / "backups"
    return p


def _iter_backup_files(d: Path) -> list[BackupFile]:
    if not d.exists():
        return []
    out: list[BackupFile] = []
    for child in d.iterdir():
        if not child.is_file():
            continue
        if _BACKUP_RE.match(child.name):
            out.append(BackupFile(path=child, mtime=child.stat().st_mtime))
    out.sort(key=lambda b: b.mtime, reverse=True)  # newest first
    return out


class Command(BaseCommand):
    help = "Prune database backup files in EZ360_BACKUP_DIR using retention rules."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without deleting anything.",
        )
        parser.add_argument(
            "--retention-days",
            type=int,
            default=None,
            help="Override BACKUP_RETENTION_DAYS for this run.",
        )
        parser.add_argument(
            "--max-files",
            type=int,
            default=None,
            help="Override BACKUP_MAX_FILES for this run (keeps newest N).",
        )

    def handle(self, *args, **options):
        d = _backup_dir()
        files = _iter_backup_files(d)

        retention_days = options["retention_days"]
        if retention_days is None:
            retention_days = int(getattr(settings, "BACKUP_RETENTION_DAYS", 30) or 30)

        max_files = options["max_files"]
        if max_files is None:
            mf = getattr(settings, "BACKUP_MAX_FILES", None)
            max_files = int(mf) if mf not in (None, "",) else None

        cutoff = time.time() - (retention_days * 86400)

        to_delete: list[BackupFile] = []
        # Rule 1: age-based
        for bf in files:
            if bf.mtime < cutoff:
                to_delete.append(bf)

        # Rule 2: count-based (keep newest max_files)
        if max_files is not None and max_files >= 0 and len(files) > max_files:
            for bf in files[max_files:]:
                if bf not in to_delete:
                    to_delete.append(bf)

        # Deduplicate and sort deletions oldest-first for nicer output
        uniq = {bf.path: bf for bf in to_delete}
        delete_list = sorted(uniq.values(), key=lambda b: b.mtime)

        if not delete_list:
            self.stdout.write(self.style.SUCCESS(f"No backups to prune in {d}"))
            return

        self.stdout.write(f"Backup dir: {d}")
        self.stdout.write(f"Retention days: {retention_days}")
        self.stdout.write(f"Max files: {max_files if max_files is not None else 'disabled'}")
        self.stdout.write(f"Candidates: {len(delete_list)}")

        dry_run = bool(options["dry_run"])
        deleted = 0
        for bf in delete_list:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(bf.mtime))
            if dry_run:
                self.stdout.write(f"DRY-RUN delete: {bf.path.name} (mtime {ts})")
                continue
            try:
                bf.path.unlink()
                deleted += 1
                self.stdout.write(self.style.WARNING(f"Deleted: {bf.path.name} (mtime {ts})"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Failed to delete {bf.path.name}: {e}"))

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run complete."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Pruned {deleted} backup file(s)."))
