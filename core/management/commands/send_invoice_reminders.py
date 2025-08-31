# core/management/commands/send_invoice_reminders.py
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.db.models import F, Value, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce

from core.models import Invoice
from core.services import recalc_invoice

class Command(BaseCommand):
    help = "Send scheduled invoice reminders based on INVOICE_REMINDER_SCHEDULE"

    def handle(self, *args, **opts):
        schedule = getattr(settings, "INVOICE_REMINDER_SCHEDULE", [-3, 0, 3, 7, 14])
        today = timezone.now().date()

        # balance expression (if you prefer not to call recalc for a batch)
        balance_expr = ExpressionWrapper(
            Coalesce(F("total"), Value(0, output_field=DecimalField())) -
            Coalesce(F("amount_paid"), Value(0, output_field=DecimalField())),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )

        qs = (
            Invoice.objects
            .exclude(status=Invoice.VOID)
            .filter(allow_reminders=True, due_date__isnull=False)
            .annotate(balance=balance_expr)
            .filter(balance__gt=0)
            .select_related("client", "project", "company")
            .order_by("due_date")
        )

        sent_count = 0
        for inv in qs:
            # ensure computed fields are fresh if needed
            try:
                recalc_invoice(inv)
            except Exception:
                pass

            if not getattr(inv.client, "email", None):
                continue

            days = (today - inv.due_date).days  # type: ignore # negative = before due
            # skip if this offset isn’t scheduled
            if days not in schedule:
                continue

            # skip if already sent at this offset
            already = set([p.strip() for p in (inv.reminder_log or "").split(",") if p.strip()])
            key = str(days)
            if key in already:
                continue

            # Subject/body
            if days > 0:
                subject = f"Overdue: Invoice {inv.number} ({days} day{'s' if days != 1 else ''} past due)"
            elif days == 0:
                subject = f"Due today: Invoice {inv.number}"
            else:
                subject = f"Upcoming: Invoice {inv.number} due {inv.due_date}"

            body = render_to_string(
                "core/email/invoice_reminder_email.txt",
                {"inv": inv, "site_url": settings.SITE_URL, "days": days},
            )

            # Attach PDF
            from core.views import _render_pdf_from_html  # lazy import path
            html = render_to_string("core/pdf/invoice.html", {"inv": inv})
            pdf_bytes = _render_pdf_from_html(html, base_url=f"{settings.SITE_URL}/")

            email = EmailMessage(
                subject=subject,
                body=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                to=[inv.client.email],
            )
            email.attach(f"invoice_{inv.number}.pdf", pdf_bytes, "application/pdf")
            email.send(fail_silently=False)

            inv.last_reminder_sent_at = timezone.now()
            inv.reminder_log = (inv.reminder_log + ("," if inv.reminder_log else "") + key)
            inv.save(update_fields=["last_reminder_sent_at", "reminder_log"])
            sent_count += 1

        self.stdout.write(self.style.SUCCESS(f"Invoice reminders sent: {sent_count}"))
