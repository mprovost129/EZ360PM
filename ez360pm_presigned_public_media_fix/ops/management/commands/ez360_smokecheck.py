from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import ProgrammingError


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str = ""


class Command(BaseCommand):
    help = "Run a lightweight post-deploy smoke check (migrations + critical tables)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fail-fast",
            action="store_true",
            help="Stop at the first failing check.",
        )

    def handle(self, *args, **options):
        fail_fast = bool(options.get("fail_fast"))

        results: list[CheckResult] = []

        # 1) Pending migrations
        pending = []
        pending_error = ""
        try:
            conn = connections["default"]
            executor = MigrationExecutor(conn)
            targets = executor.loader.graph.leaf_nodes()
            plan = executor.migration_plan(targets)
            pending = [(m.app_label, m.name) for (m, backwards) in plan if not backwards]
        except Exception as exc:
            pending_error = str(exc)

        mig_ok = (not pending) and (not pending_error)
        mig_details = "No pending migrations." if mig_ok else (pending_error or f"Pending migrations: {len(pending)}")
        results.append(CheckResult("Migrations applied", mig_ok, mig_details))
        if fail_fast and not mig_ok:
            self._print(results, pending)
            raise SystemExit(1)

        # 2) ops.SiteConfig table exists
        site_ok = True
        site_details = "ops.SiteConfig OK."
        try:
            from ops.models import SiteConfig

            SiteConfig.get_solo()
        except ProgrammingError as exc:
            site_ok = False
            site_details = f"ops_siteconfig missing table: {exc.__class__.__name__}"
        except Exception as exc:
            site_ok = False
            site_details = str(exc)

        results.append(CheckResult("Singleton tables present", site_ok, site_details))
        if fail_fast and not site_ok:
            self._print(results, pending)
            raise SystemExit(1)

        # 3) Auth model readable
        auth_ok = True
        auth_details = "User model OK."
        try:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            _ = User.objects.count()
        except Exception as exc:
            auth_ok = False
            auth_details = str(exc)

        results.append(CheckResult("Auth model readable", auth_ok, auth_details))

        self._print(results, pending)

        if any(not r.ok for r in results):
            raise SystemExit(1)

    def _print(self, results: list[CheckResult], pending: list[tuple[str, str]]):
        self.stdout.write("\nEZ360PM smoke check\n" + "-" * 22)
        for r in results:
            status = "OK" if r.ok else "FAIL"
            self.stdout.write(f"[{status}] {r.name} — {r.details}")
        if pending:
            self.stdout.write("\nPending migrations:")
            for app_label, name in pending[:50]:
                self.stdout.write(f"  - {app_label}.{name}")
