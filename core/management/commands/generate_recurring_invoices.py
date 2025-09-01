# core/management/commands/run_recurring_invoices.py
from __future__ import annotations

from datetime import date as date_cls
from typing import Iterable, Optional

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction

from core.models import RecurringPlan, Invoice
from core.services import (
    generate_invoice_from_plan,
    email_invoice_default,
    advance_plan_after_run,
)


class Command(BaseCommand):
    help = (
        "Generate invoices for active recurring plans whose next_run_date is on or before the run date. "
        "Supports dry-run, company scoping, custom run date, and email overrides."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be generated without creating invoices or changing plans.",
        )
        parser.add_argument(
            "--company",
            type=int,
            default=0,
            help="Restrict to a single company ID.",
        )
        parser.add_argument(
            "--date",
            type=str,
            default="",
            help="Run as of this ISO date (YYYY-MM-DD). Defaults to today in server TZ.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop after generating this many invoices (0 = no limit).",
        )
        email_group = parser.add_mutually_exclusive_group()
        email_group.add_argument(
            "--send-email",
            action="store_true",
            help="Force sending email for each generated invoice (ignores plan.auto_email).",
        )
        email_group.add_argument(
            "--no-email",
            action="store_true",
            help="Do not send any emails (ignores plan.auto_email).",
        )

    # -------------------------
    # Helpers
    # -------------------------

    def _parse_run_date(self, arg: str) -> date_cls:
        if not arg:
            return timezone.localdate()
        try:
            return date_cls.fromisoformat(arg)
        except Exception as e:
            raise CommandError(f"Invalid --date value {arg!r}: {e}")

    def _should_email(self, plan: RecurringPlan, *, force: bool, skip: bool) -> bool:
        if skip:
            return False
        if force:
            return True
        return bool(getattr(plan, "auto_email", False))

    def _eligible_queryset(self, *, company_id: int):
        qs = (
            RecurringPlan.objects
            .select_related("company", "client", "project", "template_invoice")
            .order_by("next_run_date", "id")
        )
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs

    # -------------------------
    # Main
    # -------------------------

    def handle(self, *args, **opts):
        dry_run: bool = bool(opts.get("dry_run"))
        company_id: int = int(opts.get("company") or 0)
        run_date: date_cls = self._parse_run_date(opts.get("date") or "")
        limit: int = int(opts.get("limit") or 0)
        force_email: bool = bool(opts.get("send_email"))
        skip_email: bool = bool(opts.get("no_email"))

        qs = self._eligible_queryset(company_id=company_id)

        self.stdout.write(
            f"Recurring run on {run_date.isoformat()} "
            f"(company={'ALL' if not company_id else company_id}, "
            f"dry_run={dry_run}, limit={limit or '∞'}, "
            f"email={'FORCE' if force_email else ('SKIP' if skip_email else 'plan.auto_email')})"
        )

        generated = 0
        scanned = 0

        iterable: Iterable[RecurringPlan] = qs.iterator(chunk_size=500)

        for plan in iterable:
            scanned += 1

            # Quick guards
            try:
                if not plan.is_active():
                    continue
                if not plan.next_run_date:
                    # If there's no next_run_date set yet, skip safely
                    continue
                if plan.next_run_date > run_date:
                    continue
            except Exception as e:
                self.stderr.write(self.style.WARNING(f"Skipping plan #{plan.id} due to guard error: {e}")) # type: ignore
                continue

            # Decide if we will email
            do_email = self._should_email(plan, force=force_email, skip=skip_email)

            # Dry-run logging
            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] Would generate invoice for plan #{plan.id} " # type: ignore
                    f"({plan.title!r}) due {plan.next_run_date} "
                    f"{'with email' if do_email else 'without email'}"
                )
                generated += 1
                if limit and generated >= limit:
                    break
                continue

            # Real run: per-plan isolation
            try:
                with transaction.atomic():
                    inv: Invoice = generate_invoice_from_plan(plan)

                    sent_email = False
                    if do_email:
                        try:
                            email_invoice_default(inv)
                            inv.status = Invoice.SENT
                            inv.save(update_fields=["status"])
                            sent_email = True
                        except Exception as e:
                            # Email failure shouldn't rollback invoice creation
                            self.stderr.write(self.style.WARNING(
                                f"Email failed for invoice {inv.number or inv.pk} (plan #{plan.id}): {e}" # type: ignore
                            ))

                    advance_plan_after_run(plan)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Generated invoice {inv.number or inv.pk} "
                        f"from plan #{plan.id} ({plan.title!r})" # type: ignore
                        f"{' and emailed' if sent_email else ''}."
                    )
                )
                generated += 1
                if limit and generated >= limit:
                    break

            except Exception as e:
                # Keep batch going on individual failure
                self.stderr.write(
                    self.style.ERROR(f"Failed generating invoice for plan #{plan.id}: {e}") # type: ignore
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Recurring invoices processed: scanned={scanned}, generated={generated}, dry_run={dry_run}"
            )
        )
