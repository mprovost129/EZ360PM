from __future__ import annotations

import json
import os
from typing import Any

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from core.launch_checks import run_launch_checks


class Command(BaseCommand):
    """Deploy preflight checks.

    Intended for CI/staging/prod before a release is promoted.

    Runs:
      - Django system checks (manage.py check)
      - Launch checks (core.launch_checks)

    Outputs a JSON report and exits non-zero if any *error* level explains ok=False.
    """

    help = "Run deploy preflight: Django system checks + launch checks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output JSON only (no human formatting).",
        )

    def handle(self, *args: Any, **options: Any):
        # Django checks
        # If system checks fail, Django will raise SystemCheckError (non-zero).
        call_command("check")

        # Pending migrations (unapplied)
        pending = []
        try:
            connection = connections["default"]
            executor = MigrationExecutor(connection)
            targets = executor.loader.graph.leaf_nodes()
            plan = executor.migration_plan(targets)
            # plan contains (migration, backwards) tuples; backwards should be False for forward plan.
            pending = [str(mig) for (mig, backwards) in plan if not backwards]
        except Exception:
            # Best-effort only; do not block check() failures.
            pending = []


        results = run_launch_checks()
        failed_errors = [r for r in results if not r.get("ok") and r.get("level") == "error"]

        report = {
            "pending_migrations": pending,
            "launch_checks": results,
            "summary": {
                "total": len(results),
                "failed_errors": len(failed_errors),
                "failed_warns": sum(1 for r in results if not r.get("ok") and r.get("level") == "warn"),
                "pending_migrations": len(pending),
            },
        }

        if options.get("json"):
            self.stdout.write(json.dumps(report, indent=2, default=str))
        else:
            self.stdout.write(self.style.MIGRATE_HEADING("Launch checks"))
            for r in results:
                level = str(r.get("level") or "").upper()
                ok = bool(r.get("ok"))
                prefix = "OK" if ok else "FAIL"
                line = f"[{prefix}] {level:<5} {r.get('id')} — {r.get('title')}"
                self.stdout.write(line)
                msg = (r.get("message") or "").strip()
                if msg:
                    self.stdout.write(f"       {msg}")
                hint = (r.get("hint") or "").strip()
                if hint and not ok:
                    self.stdout.write(f"       Hint: {hint}")

            self.stdout.write("\n" + json.dumps(report["summary"], indent=2))

        require_no_pending = os.getenv("PREFLIGHT_REQUIRE_NO_PENDING_MIGRATIONS", "1").strip() not in ("0", "false", "False")
        if require_no_pending and pending:
            # Treat as an error-level preflight failure.
            raise SystemExit(3)

        if failed_errors:
            raise SystemExit(2)
