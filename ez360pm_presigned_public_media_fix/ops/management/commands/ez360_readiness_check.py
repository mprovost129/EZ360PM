from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.core.management import BaseCommand, call_command
from django.core.mail import get_connection
from django.db import connections
from django.db.migrations.executor import MigrationExecutor


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str = ""


def _env(name: str) -> str:
    return str(os.environ.get(name, "")).strip()


class Command(BaseCommand):
    help = "Run a production readiness checklist (env, DB, migrations, storage, email). Non-destructive."

    def add_arguments(self, parser):
        parser.add_argument("--verbose", action="store_true", help="Include extra diagnostic details.")

    def handle(self, *args, **opts):
        verbose: bool = bool(opts.get("verbose"))

        results: list[CheckResult] = []
        results.extend(self._check_env())
        results.extend(self._check_db(verbose=verbose))
        results.extend(self._check_migrations(verbose=verbose))
        results.extend(self._check_storage(verbose=verbose))
        results.extend(self._check_staticfiles(verbose=verbose))
        results.extend(self._check_email(verbose=verbose))

        ok = all(r.ok for r in results)
        width = max(len(r.name) for r in results) if results else 10

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("EZ360PM Readiness Check"))
        self.stdout.write(self.style.HTTP_INFO(f"Settings module: {getattr(settings, 'SETTINGS_MODULE', os.environ.get('DJANGO_SETTINGS_MODULE',''))}"))
        self.stdout.write(self.style.HTTP_INFO(f"DEBUG: {settings.DEBUG}"))
        self.stdout.write("")

        for r in results:
            status = self.style.SUCCESS("OK") if r.ok else self.style.ERROR("FAIL")
            self.stdout.write(f"{status}  {r.name.ljust(width)}  {r.details}".rstrip())

        self.stdout.write("")
        if ok:
            self.stdout.write(self.style.SUCCESS("Readiness check PASSED."))
            return
        raise SystemExit(2)

    def _check_env(self) -> Iterable[CheckResult]:
        checks: list[CheckResult] = []

        # We don't hard-fail on everything in dev. We do enforce that SECRET_KEY is not the Django default.
        secret = getattr(settings, "SECRET_KEY", "")
        if not secret or secret.startswith("django-insecure"):
            checks.append(CheckResult("SECRET_KEY", False, "Missing or insecure default (django-insecure*)."))
        else:
            checks.append(CheckResult("SECRET_KEY", True))

        # Database URL (if used)
        db_url = _env("DATABASE_URL")
        if db_url:
            checks.append(CheckResult("DATABASE_URL", True))
        else:
            # Not always required (SQLite/local). Warn only.
            checks.append(CheckResult("DATABASE_URL", True, "Not set (OK for local dev)."))

        # Stripe
        stripe_key = _env("STRIPE_SECRET_KEY")
        if stripe_key:
            checks.append(CheckResult("STRIPE_SECRET_KEY", True))
        else:
            checks.append(CheckResult("STRIPE_SECRET_KEY", True, "Not set (Stripe features disabled)."))

        # S3
        use_s3 = getattr(settings, "USE_S3", False)
        if use_s3:
            bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
            if bucket:
                checks.append(CheckResult("S3 bucket", True, f"USE_S3=True ({bucket})"))
            else:
                checks.append(CheckResult("S3 bucket", False, "USE_S3=True but AWS_STORAGE_BUCKET_NAME is empty."))
        else:
            checks.append(CheckResult("S3 bucket", True, "USE_S3=False (local media)."))

        return checks

    def _check_db(self, *, verbose: bool) -> Iterable[CheckResult]:
        checks: list[CheckResult] = []
        try:
            conn = connections["default"]
            conn.ensure_connection()
            vendor = conn.vendor
            name = conn.settings_dict.get("NAME", "")
            checks.append(CheckResult("Database connection", True, f"{vendor} ({name})" if verbose else vendor))
        except Exception as e:
            checks.append(CheckResult("Database connection", False, repr(e)))
        return checks

    def _check_migrations(self, *, verbose: bool) -> Iterable[CheckResult]:
        checks: list[CheckResult] = []
        try:
            executor = MigrationExecutor(connections["default"])
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if plan:
                checks.append(CheckResult("Migrations", False, f"{len(plan)} pending"))
            else:
                checks.append(CheckResult("Migrations", True, "None pending"))
        except Exception as e:
            checks.append(CheckResult("Migrations", False, repr(e)))
        return checks

    def _check_storage(self, *, verbose: bool) -> Iterable[CheckResult]:
        checks: list[CheckResult] = []
        try:
            # If local storage, ensure MEDIA_ROOT exists and is writable.
            if not getattr(settings, "USE_S3", False):
                media_root = Path(getattr(settings, "MEDIA_ROOT", ""))
                if not str(media_root):
                    return [CheckResult("Media storage", False, "MEDIA_ROOT not configured.")]
                media_root.mkdir(parents=True, exist_ok=True)
                test_file = media_root / ".write_test"
                test_file.write_text("ok", encoding="utf-8")
                test_file.unlink(missing_ok=True)
                checks.append(CheckResult("Media storage", True, str(media_root) if verbose else "Writable"))
            else:
                # For S3 we can't verify network access here. Just report configuration.
                checks.append(CheckResult("Media storage", True, "S3 configured"))
        except Exception as e:
            checks.append(CheckResult("Media storage", False, repr(e)))
        return checks

    

    def _check_staticfiles(self, verbose: bool = False) -> Iterable[CheckResult]:
        checks: list[CheckResult] = []

        static_root = getattr(settings, "STATIC_ROOT", None)
        storages = getattr(settings, "STORAGES", {}) or {}
        static_storage = storages.get("staticfiles") or {}
        backend = static_storage.get("BACKEND") or ""

        details = []
        if backend:
            details.append(f"backend={backend}")

        if static_root:
            try:
                p = Path(static_root)
                if not p.exists():
                    # In prod we expect collectstatic to have populated STATIC_ROOT.
                    if not settings.DEBUG:
                        checks.append(CheckResult("Static files (STATIC_ROOT)", False, f"{static_root} does not exist (run collectstatic)."))
                        return checks
                    checks.append(CheckResult("Static files (STATIC_ROOT)", True, f"{static_root} missing (dev OK)."))
                    return checks

                # Write test only for local filesystem static roots.
                if p.is_dir():
                    test_file = p / ".write_test"
                    try:
                        test_file.write_text("ok", encoding="utf-8")
                        test_file.unlink(missing_ok=True)
                        details.append("writable")
                    except Exception as exc:
                        if not settings.DEBUG:
                            checks.append(CheckResult("Static files (STATIC_ROOT)", False, f"not writable: {exc}"))
                            return checks
                        details.append(f"not writable (dev OK): {exc}")

                checks.append(CheckResult("Static files (STATIC_ROOT)", True, ", ".join(details) if details else "OK"))
                return checks
            except Exception as exc:
                checks.append(CheckResult("Static files (STATIC_ROOT)", False, str(exc)))
                return checks

        # No STATIC_ROOT set: that's fine in dev, but not ideal in prod.
        if settings.DEBUG:
            checks.append(CheckResult("Static files (STATIC_ROOT)", True, "STATIC_ROOT not set (dev OK)."))
        else:
            checks.append(CheckResult("Static files (STATIC_ROOT)", False, "STATIC_ROOT not set."))
        return checks

def _check_email(self, *, verbose: bool) -> Iterable[CheckResult]:
        checks: list[CheckResult] = []
        try:
            backend = getattr(settings, "EMAIL_BACKEND", "")
            # Try to open a connection (won't send).
            conn = get_connection(fail_silently=False)
            conn.open()
            conn.close()
            checks.append(CheckResult("Email backend", True, backend if verbose else "Connection OK"))
        except Exception as e:
            # Email is optional in dev; fail in prod-like settings.
            if settings.DEBUG:
                checks.append(CheckResult("Email backend", True, f"Not configured (OK for dev): {e!r}"))
            else:
                checks.append(CheckResult("Email backend", False, repr(e)))
        return checks
