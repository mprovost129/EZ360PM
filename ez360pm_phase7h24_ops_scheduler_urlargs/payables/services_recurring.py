from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db import transaction
from django.utils import timezone

from audit.services import log_event
from companies.models import Company, EmployeeProfile

from .models import Bill, BillLineItem, BillStatus, RecurringBillPlan, RecurringBillFrequency


def _add_months(d: date, months: int) -> date:
    """Add months to a date with safe rollover.

    Example: Jan 31 + 1 month -> Feb 28/29 (last day of month).
    """
    if months == 0:
        return d
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    # clamp day to last day of target month
    import calendar as _cal
    last_day = _cal.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # Feb 29 -> Feb 28 on non-leap years
        return d.replace(year=d.year + years, day=28)


def compute_next_run(*, current_next_run: date, frequency: str) -> date:
    if frequency == RecurringBillFrequency.WEEKLY:
        return current_next_run + timedelta(days=7)
    if frequency == RecurringBillFrequency.MONTHLY:
        return _add_months(current_next_run, 1)
    if frequency == RecurringBillFrequency.YEARLY:
        return _add_years(current_next_run, 1)
    # defensive default
    return _add_months(current_next_run, 1)


@transaction.atomic
def generate_bill_from_plan(
    *,
    plan: RecurringBillPlan,
    run_date: date | None = None,
    actor: EmployeeProfile | None = None,
    force: bool = False,
) -> Bill | None:
    """Generate a Bill from a RecurringBillPlan.

    - If not force: only generates if plan.next_run <= run_date and plan is_active.
    - Always advances plan.next_run to the next occurrence when a bill is generated.
    """
    if plan.deleted_at:
        return None

    if not plan.is_active and not force:
        return None

    run_date = run_date or timezone.localdate()

    if (not force) and plan.next_run and plan.next_run > run_date:
        return None

    company = plan.company

    bill = Bill.objects.create(
        company=company,
        vendor=plan.vendor,
        bill_number="",
        issue_date=run_date,
        due_date=run_date,
        status=BillStatus.DRAFT,
        tax_cents=0,
        created_by=actor,
        updated_by_user=getattr(actor, "user", None) if actor else None,
    )

    BillLineItem.objects.create(
        bill=bill,
        description="Recurring bill",
        quantity=1,
        unit_price_cents=int(plan.amount_cents or 0),
        expense_account=plan.expense_account,
    )

    bill.recalc_totals()
    bill.save(update_fields=["subtotal_cents", "total_cents", "amount_paid_cents", "balance_cents", "tax_cents", "updated_at", "revision"])

    if plan.auto_post:
        bill.post(actor=actor)

    # advance schedule
    old_next = plan.next_run
    plan.last_run_at = timezone.now()
    if old_next:
        plan.next_run = compute_next_run(current_next_run=old_next, frequency=plan.frequency)
    else:
        plan.next_run = compute_next_run(current_next_run=run_date, frequency=plan.frequency)
    plan.updated_by_user = getattr(actor, "user", None) if actor else None
    plan.save(update_fields=["next_run", "last_run_at", "updated_at", "revision", "updated_by_user"])

    # audit
    try:
        log_event(
            company=company,
            actor=actor,
            event_type="payables.recurring_bill.generated",
            object_type="RecurringBillPlan",
            object_id=plan.id,
            summary="Recurring bill generated",
            payload={
                "plan_id": str(plan.id),
                "bill_id": str(bill.id),
                "run_date": str(run_date),
                "old_next_run": str(old_next) if old_next else "",
                "new_next_run": str(plan.next_run) if plan.next_run else "",
                "auto_post": bool(plan.auto_post),
            },
        )
    except Exception:
        # audit should not block bill generation
        pass

    return bill


@transaction.atomic
def run_due_recurring_bills(*, company: Company | None = None, actor: EmployeeProfile | None = None) -> int:
    """Run all due recurring bills (next_run <= today). Returns count created."""
    today = timezone.localdate()
    qs = RecurringBillPlan.objects.filter(deleted_at__isnull=True, is_active=True, next_run__lte=today)
    if company is not None:
        qs = qs.filter(company=company)

    created = 0
    for plan in qs.select_related("company", "vendor", "expense_account").order_by("next_run", "id"):
        bill = generate_bill_from_plan(plan=plan, run_date=today, actor=actor, force=False)
        if bill:
            created += 1
    return created
