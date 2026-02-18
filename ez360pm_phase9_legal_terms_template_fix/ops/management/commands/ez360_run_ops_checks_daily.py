from __future__ import annotations

import io
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from companies.models import Company
from ops.models import OpsCheckKind, OpsCheckRun
from ops.models import OpsAlertLevel, OpsAlertSource
from ops.services_alerts import create_ops_alert
from core.ops_alerts import alert_admins


class Command(BaseCommand):
    help = "Run ops-grade checks and persist evidence (intended for daily scheduler/cron)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--company-id",
            default="",
            help="Optional company UUID to run company-scoped checks (smoke/invariants/idempotency).",
        )
        parser.add_argument("--quiet", action="store_true", help="Pass --quiet to checks when supported.")
        parser.add_argument("--fail-fast", action="store_true", help="Pass --fail-fast to checks when supported.")
        parser.add_argument(
            "--created-by-email",
            default="system@ez360pm",
            help="Email to record as the creator for persisted runs (default: system@ez360pm).",
        )
        parser.add_argument(
            "--include-smoke",
            action="store_true",
            help="Also run smoke test (requires --company-id).",
        )
        parser.add_argument(
            "--max-output-chars",
            type=int,
            default=200000,
            help="Max output stored per run (default: 200000).",
        )

    def handle(self, *args, **opts):
        company_id = (opts.get("company_id") or "").strip()
        quiet = bool(opts.get("quiet"))
        fail_fast = bool(opts.get("fail_fast"))
        created_by_email = (opts.get("created_by_email") or "").strip()[:254] or "system@ez360pm"
        include_smoke = bool(opts.get("include_smoke"))
        max_chars = int(opts.get("max_output_chars") or 200000)

        company = None
        if company_id:
            company = Company.objects.filter(pk=company_id).first()
            if company is None:
                raise SystemExit(f"Company not found: {company_id}")

        def _store(kind: str, args_dict: dict, ok: bool, duration_ms: int, out_text: str):
            stored = out_text or "(no output)"
            if len(stored) > max_chars:
                stored = stored[:max_chars] + "\n\n[output truncated]"
            OpsCheckRun.objects.create(
                created_by_email=created_by_email,
                company=company,
                kind=kind,
                args=args_dict or {},
                is_ok=ok,
                duration_ms=max(duration_ms, 0),
                output_text=stored,
            )

        def _run(kind: str, cmd: str, **kwargs) -> bool:
            buf = io.StringIO()
            started = time.time()
            ok = False
            try:
                call_command(cmd, stdout=buf, stderr=buf, **kwargs)
                ok = True
            except SystemExit as e:
                code = getattr(e, "code", 1)
                ok = (code == 0)
                buf.write(f"\n(exit {code})")
            except Exception as e:
                buf.write(f"\n(exception) {e!r}")
                ok = False
            duration_ms = int((time.time() - started) * 1000)

            _store(kind, kwargs, ok, duration_ms, buf.getvalue())
            results.append((kind, ok))
            return ok

        self.stdout.write("Running scheduled ops checks...")

        results: list[tuple[str, bool]] = []  # (kind, ok)

        # Global checks
        _run(OpsCheckKind.READINESS, "ez360_readiness_check")

        kwargs_common = {}
        if quiet:
            kwargs_common["quiet"] = True
        if fail_fast:
            kwargs_common["fail_fast"] = True

        _run(OpsCheckKind.TEMPLATE_SANITY, "ez360_template_sanity_check", **kwargs_common)
        _run(OpsCheckKind.URL_SANITY, "ez360_url_sanity_check", **kwargs_common)

        if company is not None:
            # Company-scoped checks
            _run(OpsCheckKind.INVARIANTS, "ez360_invariants_check", company_id=str(company.id), **kwargs_common)
            _run(OpsCheckKind.IDEMPOTENCY, "ez360_idempotency_scan", company_id=str(company.id), **kwargs_common)
            if include_smoke:
                _run(OpsCheckKind.SMOKE, "ez360_smoke_test", company_id=str(company.id))



        failed_kinds = [k for (k, ok) in results if not ok]
        if failed_kinds:
            title = "Daily ops checks failed"
            msg_lines = [
        f"Environment: {getattr(settings, 'ENVIRONMENT', '')}",
        f"Company: {company.name if company else '(none)'}",
        f"Failed checks: {', '.join(failed_kinds)}",
        f"Runs saved: {len(results)}",
            ]
            message = "\n".join([l for l in msg_lines if l])
            # Persist an ops alert event + optional webhook.
            create_ops_alert(
        title=title,
        message=message,
        level=OpsAlertLevel.ERROR,
        source=OpsAlertSource.LAUNCH_GATE,
        company=company,
        details={"failed_kinds": failed_kinds, "total_runs": len(results)},
            )
            # Optional: email configured ADMINS (best-effort).
            alert_admins(title, message, fail_silently=True, extra={"failed_kinds": ", ".join(failed_kinds)})
            self.stdout.write(self.style.ERROR("FAILED: " + message))
            raise SystemExit(2)

        self.stdout.write("OK: scheduled ops checks completed and evidence saved.")
