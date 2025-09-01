# core/management/commands/send_invoice_reminders.py
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Sequence, Optional

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.db.models import F, Value, QuerySet, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce

from core.models import Invoice
from core.services import recalc_invoice


class Command(BaseCommand):
    help = "Send scheduled invoice reminders based on INVOICE_REMINDER_SCHEDULE"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List invoices that would get reminders without sending emails or updating records.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of reminders to send (0 = no limit).",
        )
        parser.add_argument(
            "--company",
            type=int,
            default=0,
            help="Restrict to a single company ID.",
        )
        parser.add_argument(
            "--days",
            type=str,
            default="",
            help=(
                "Override schedule with a CSV list of integer day offsets "
                "(e.g. '-3,0,3,7,14'). If omitted, uses settings.INVOICE_REMINDER_SCHEDULE."
            ),
        )

    # ---------------------------
    # Helpers
    # ---------------------------

    def _get_schedule(self, days_arg: str) -> Sequence[int]:
        if days_arg:
            out: list[int] = []
            for tok in days_arg.split(","):
                tok = tok.strip()
                if not tok:
                    continue
                try:
                    out.append(int(tok))
                except ValueError:
                    self.stderr.write(self.style.WARNING(f"Ignoring invalid days offset: {tok!r}"))
            return sorted(set(out))
        # Fall back to settings
        default = getattr(settings, "INVOICE_REMINDER_SCHEDULE", [-3, 0, 3, 7, 14])
        try:
            # ensure ints & uniqueness
            sched = sorted(set(int(x) for x in default))
        except Exception:
            sched = [-3, 0, 3, 7, 14]
        return sched

    def _query(self, company_id: int) -> QuerySet[Invoice]:
        """
        Select invoices with:
          - due_date present
          - positive balance
          - reminders allowed
          - not VOID or DRAFT
        """
        # Accurate Decimal 0.00 value for Coalesce and arithmetic
        zero = Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))
        balance_expr = ExpressionWrapper(
            Coalesce(F("total"), zero) - Coalesce(F("amount_paid"), zero),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )

        qs = (
            Invoice.objects
            .exclude(status=Invoice.VOID)
            .exclude(status=Invoice.DRAFT)
            .filter(allow_reminders=True, due_date__isnull=False)
            .annotate(balance=balance_expr)
            .filter(balance__gt=0)
            .select_related("client", "project", "company")
            .order_by("due_date", "id")
        )
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs

    def _subject_for_days(self, inv: Invoice, days: int) -> str:
        prefix = getattr(settings, "EMAIL_SUBJECT_PREFIX", "[EZ360PM] ")
        if days > 0:
            base = f"Overdue: Invoice {inv.number} ({days} day{'s' if days != 1 else ''} past due)"
        elif days == 0:
            base = f"Due today: Invoice {inv.number}"
        else:
            base = f"Upcoming: Invoice {inv.number} due {inv.due_date}"
        return f"{prefix}{base}"

    def _render_pdf_or_none(self, inv: Invoice) -> Optional[bytes]:
        """
        Try to render PDF. If WeasyPrint (or deps) aren't available, skip attachment gracefully.
        """
        try:
            from core.views import _render_pdf_from_html  # lazy import to avoid import-time deps
            html = render_to_string("core/pdf/invoice.html", {"inv": inv})
            base_url = getattr(settings, "SITE_URL", "")
            if base_url and not base_url.endswith("/"):
                base_url = f"{base_url}/"
            # If SITE_URL is not configured, still try with a relative base_url to avoid raising
            base_url = base_url or "/"
            return _render_pdf_from_html(html, base_url=base_url)
        except Exception as e:
            # Don’t fail the entire run for a PDF error — we can still send a reminder.
            self.stderr.write(self.style.WARNING(f"PDF render failed for {inv.number}: {e}"))
            return None

    def _already_sent_for_offset(self, inv: Invoice, days: int) -> bool:
        log = getattr(inv, "reminder_log", "") or ""
        if not log:
            return False
        seen = {t.strip() for t in log.split(",") if t.strip()}
        return str(days) in seen

    def _append_offset_to_log(self, inv: Invoice, days: int) -> str:
        log = getattr(inv, "reminder_log", "") or ""
        key = str(days)
        if not log:
            return key
        if key in {t.strip() for t in log.split(",") if t.strip()}:
            return log  # idempotent
        return f"{log},{key}"

    def _send_one(self, inv: Invoice, days: int, *, dry_run: bool) -> bool:
        """
        Returns True if (would be) sent.
        """
        # Freshen totals & status; continue on error
        try:
            recalc_invoice(inv)
        except Exception:
            pass

        to_email = getattr(getattr(inv, "client", None), "email", "") or ""
        if not to_email:
            self.stdout.write(f"- Skip {inv.number}: client has no email")
            return False

        # Build email body
        ctx = {"inv": inv, "site_url": getattr(settings, "SITE_URL", ""), "days": days}
        body = render_to_string("core/email/invoice_reminder_email.txt", ctx)

        # Subject
        subject = self._subject_for_days(inv, days)

        # PDF (optional)
        pdf_bytes = self._render_pdf_or_none(inv)

        if dry_run:
            self.stdout.write(f"[DRY RUN] Would send → {inv.number} to {to_email} (days offset {days})")
            return True

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[to_email],
        )
        if pdf_bytes:
            email.attach(f"invoice_{inv.number}.pdf", pdf_bytes, "application/pdf")
        email.send(fail_silently=False)
        return True

    # ---------------------------
    # Entry point
    # ---------------------------

    def handle(self, *args, **opts):
        schedule = self._get_schedule(opts.get("days") or "")
        if not schedule:
            self.stderr.write(self.style.WARNING("Empty reminder schedule; nothing to do."))
            return

        today = timezone.localdate()
        dry_run: bool = bool(opts.get("dry_run"))
        limit: int = int(opts.get("limit") or 0)
        company_id: int = int(opts.get("company") or 0)

        qs = self._query(company_id=company_id)

        sent_count = 0
        scanned = 0

        self.stdout.write(
            f"Running invoice reminders on {today.isoformat()} "
            f"(schedule={list(schedule)}, company={'ALL' if not company_id else company_id}, "
            f"dry_run={dry_run}, limit={limit or '∞'})"
        )

        iterable: Iterable[Invoice] = qs.iterator(chunk_size=500)

        for inv in iterable:
            scanned += 1

            # Double-check prerequisite fields
            if not inv.due_date:
                continue  # guard; queryset already filters this
            days = (today - inv.due_date).days  # negative => before due
            if days not in schedule:
                continue

            # Skip if already recorded for this offset
            if self._already_sent_for_offset(inv, days):
                continue

            # Skip if client missing or invalid email will be handled in _send_one
            # Send
            did_send = self._send_one(inv, days, dry_run=dry_run)
            if not did_send:
                continue

            # Mark log/timestamp (unless dry-run)
            if not dry_run:
                inv.last_reminder_sent_at = timezone.now()
                inv.reminder_log = self._append_offset_to_log(inv, days)
                inv.save(update_fields=["last_reminder_sent_at", "reminder_log"])

            sent_count += 1
            if limit and sent_count >= limit:
                break

        self.stdout.write(
            self.style.SUCCESS(
                f"Invoice reminders processed: scanned={scanned}, sent={sent_count}, dry_run={dry_run}"
            )
        )
