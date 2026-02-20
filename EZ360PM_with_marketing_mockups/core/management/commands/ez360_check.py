from __future__ import annotations

from django.core.management.base import BaseCommand

from core.launch_checks import run_launch_checks


class Command(BaseCommand):
    help = "Run EZ360PM launch-readiness checks (settings/env sanity)."

    def handle(self, *args, **options):
        results = run_launch_checks()
        errors = [r for r in results if not r["ok"] and r["level"] == "error"]
        warns = [r for r in results if not r["ok"] and r["level"] == "warn"]

        for r in results:
            status = "OK" if r["ok"] else r["level"].upper()
            self.stdout.write(f"[{status}] {r['id']}: {r['title']} — {r.get('message','')}")
            if r.get("hint") and not r["ok"]:
                self.stdout.write(f"        hint: {r['hint']}")

        self.stdout.write("")
        self.stdout.write(f"Total: {len(results)} | OK: {sum(1 for r in results if r['ok'])} | WARN: {len(warns)} | ERROR: {len(errors)}")

        if errors:
            self.stderr.write("Launch checks failed.")
            raise SystemExit(1)
