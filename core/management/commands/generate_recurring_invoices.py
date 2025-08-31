from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import RecurringPlan, Invoice
from core.services import generate_invoice_from_plan, email_invoice_default, advance_plan_after_run

class Command(BaseCommand):
    help = "Generate invoices for active recurring plans whose next_run_date is today or earlier."

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        plans = RecurringPlan.objects.select_related("company", "client", "project", "template_invoice")

        count = 0
        for plan in plans:
            if not plan.is_active():
                continue
            if plan.next_run_date and plan.next_run_date <= today:
                inv = generate_invoice_from_plan(plan)
                if plan.auto_email:
                    try:
                        email_invoice_default(inv)
                        inv.status = Invoice.SENT
                        inv.save(update_fields=["status"])
                    except Exception:
                        # Keep going; invoice was created even if email failed
                        pass
                advance_plan_after_run(plan)
                count += 1

        self.stdout.write(self.style.SUCCESS(f"Recurring invoices generated: {count}"))
