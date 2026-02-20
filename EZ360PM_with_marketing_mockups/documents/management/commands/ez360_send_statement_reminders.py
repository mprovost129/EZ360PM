from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from documents.models import StatementReminder, StatementReminderStatus
from documents.services_statements import send_statement_to_client


class Command(BaseCommand):
    help = "Send due statement reminders (scheduled_for <= today)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200, help="Max reminders to process")
        parser.add_argument("--dry-run", action="store_true", help="Do not send; just report")

    def handle(self, *args, **options):
        today = timezone.localdate()
        limit = int(options.get("limit") or 200)
        dry = bool(options.get("dry_run"))

        qs = (
            StatementReminder.objects.select_related("company", "client")
            .filter(status=StatementReminderStatus.SCHEDULED, scheduled_for__lte=today, deleted_at__isnull=True)
            .order_by("scheduled_for")
        )[:limit]

        processed = 0
        sent = 0
        failed = 0

        for rem in qs:
            processed += 1
            if dry:
                self.stdout.write(f"DRY RUN: would send statement reminder to {rem.recipient_email} for {rem.client_id}")
                continue
            try:
                # Always record an attempt timestamp/counter, regardless of success.
                rem.attempted_at = timezone.now()
                rem.attempt_count = int(getattr(rem, "attempt_count", 0) or 0) + 1
                rem.save(update_fields=["attempted_at", "attempt_count", "updated_at"])

                res = send_statement_to_client(
                    company=rem.company,
                    client=rem.client,
                    actor=rem.created_by,
                    to_email=rem.recipient_email,
                    date_from=rem.date_from,
                    date_to=rem.date_to,
                    attach_pdf=bool(rem.attach_pdf),
                    template_variant=getattr(rem, "tone", "friendly") or "friendly",
                )
                if res.sent:
                    rem.status = StatementReminderStatus.SENT
                    rem.sent_at = timezone.now()
                    rem.last_error = ""
                    rem.save(update_fields=["status", "sent_at", "last_error", "updated_at"])
                    sent += 1
                else:
                    rem.status = StatementReminderStatus.FAILED
                    rem.last_error = res.message
                    rem.save(update_fields=["status", "last_error", "updated_at"])
                    failed += 1
            except Exception as exc:
                rem.status = StatementReminderStatus.FAILED
                rem.last_error = str(exc)[:2000]
                # attempted_at/attempt_count are already set just before send attempt.
                rem.save(update_fields=["status", "last_error", "updated_at"])
                failed += 1

        self.stdout.write(self.style.SUCCESS(f"Processed={processed} sent={sent} failed={failed}"))
