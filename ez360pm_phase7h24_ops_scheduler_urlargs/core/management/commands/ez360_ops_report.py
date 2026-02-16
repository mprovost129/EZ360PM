from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail

from core.email_utils import format_email_subject

from core.launch_checks import run_launch_checks
from core.retention import run_prune_jobs


class Command(BaseCommand):
    help = "Run ops checks (launch readiness + retention dry-run) and optionally email ADMINS." 

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            action="store_true",
            help="Send an email to ADMINS (if configured) when errors are found.",
        )

    def handle(self, *args, **options):
        results = run_launch_checks()
        errors = [r for r in results if not r["ok"] and r["level"] == "error"]
        warns = [r for r in results if not r["ok"] and r["level"] == "warn"]

        prune = run_prune_jobs(dry_run=True)

        self.stdout.write(f"Launch checks: ok={sum(1 for r in results if r['ok'])} warn={len(warns)} error={len(errors)}")
        for r in errors + warns:
            self.stdout.write(f" - [{r['level'].upper()}] {r['name']}: {r['message']}")

        for p in prune:
            self.stdout.write(
                f"Prune dry-run {p.label}: retention_days={p.retention_days} eligible={p.eligible_count} cutoff={p.cutoff.isoformat()}"
            )

        send_email = bool(options.get("email"))
        admins = getattr(settings, "ADMINS", [])
        if send_email and admins and errors:
            to_emails = [email for _, email in admins]
            subject = f"[{getattr(settings, 'SITE_NAME', 'EZ360PM')}] Ops check failures"
            lines = [
                f"Environment: {getattr(settings, 'ENVIRONMENT', '')}",
                "",
                f"Errors ({len(errors)}):",
            ]
            for e in errors:
                lines.append(f"- {e['name']}: {e['message']}")
            if warns:
                lines.append("")
                lines.append(f"Warnings ({len(warns)}):")
                for w in warns:
                    lines.append(f"- {w['name']}: {w['message']}")
            lines.append("")
            lines.append("Retention (dry-run):")
            for p in prune:
                lines.append(f"- {p.label}: eligible={p.eligible_count} retention_days={p.retention_days}")

            send_mail(
                subject=format_email_subject(subject),
                message="\n".join(lines),
                from_email=getattr(settings, "SERVER_EMAIL", None) or getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=to_emails,
                fail_silently=True,
            )
            self.stdout.write(f"Email sent to ADMINS: {', '.join(to_emails)}")
        elif send_email and not admins:
            self.stdout.write("ADMINS not configured; skipping email.")
