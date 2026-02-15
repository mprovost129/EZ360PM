from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.backup import create_media_backup, create_postgres_dump, prune_backups


class Command(BaseCommand):
    help = "Create database (and optional media) backups with retention pruning."

    def add_arguments(self, parser):
        parser.add_argument(
            "--db",
            action="store_true",
            help="Back up the database (default if no flags are provided).",
        )
        parser.add_argument(
            "--media",
            action="store_true",
            help="Back up MEDIA_ROOT as a tar.gz (optional).",
        )
        parser.add_argument(
            "--out-dir",
            default="",
            help="Override backup directory (otherwise EZ360_BACKUP_DIR).",
        )
        parser.add_argument(
            "--keep-last",
            type=int,
            default=-1,
            help="How many recent backups to keep per type (otherwise EZ360_BACKUP_KEEP_LAST).",
        )
        parser.add_argument(
            "--max-age-days",
            type=int,
            default=-1,
            help="Delete backups older than this age in days (otherwise EZ360_BACKUP_RETENTION_DAYS).",
        )

    def handle(self, *args, **options):
        do_db = bool(options["db"])
        do_media = bool(options["media"])

        # If user didn't pass any flags, default to DB backup only.
        if not do_db and not do_media:
            do_db = True

        out_dir_raw = str(options.get("out_dir") or "").strip()
        backup_dir = Path(out_dir_raw) if out_dir_raw else Path(getattr(settings, "EZ360_BACKUP_DIR", "backups"))

        keep_last = int(options.get("keep_last", -1))
        if keep_last < 0:
            keep_last = int(getattr(settings, "EZ360_BACKUP_KEEP_LAST", 14))

        max_age_days = int(options.get("max_age_days", -1))
        if max_age_days < 0:
            max_age_days = int(getattr(settings, "EZ360_BACKUP_RETENTION_DAYS", 14))

        results = []

        if do_db:
            res = create_postgres_dump(out_dir=backup_dir, prefix="ez360pm", format_custom=True)
            results.append(res)
            self.stdout.write(self.style.SUCCESS(f"DB backup created: {res.path} ({res.size_bytes} bytes)"))

        if do_media:
            res = create_media_backup(out_dir=backup_dir, prefix="ez360pm")
            results.append(res)
            self.stdout.write(self.style.SUCCESS(f"Media backup created: {res.path} ({res.size_bytes} bytes)"))

        deleted = prune_backups(
            backup_dir=backup_dir,
            keep_last=keep_last,
            max_age_days=max_age_days,
            prefixes=("ez360pm_db_", "ez360pm_media_"),
        )
        if deleted:
            self.stdout.write(self.style.WARNING(f"Pruned old backups: {deleted} file(s) deleted"))
        else:
            self.stdout.write(self.style.SUCCESS("Prune: no files deleted"))

        self.stdout.write(self.style.SUCCESS("Backup run complete."))
