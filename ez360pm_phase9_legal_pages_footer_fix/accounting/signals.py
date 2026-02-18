from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from companies.models import Company
from .models import ensure_default_chart


@receiver(post_save, sender=Company)
def _create_default_chart(sender, instance: Company, created: bool, **kwargs):
    if created:
        ensure_default_chart(instance)


from documents.models import Document
from payments.models import Payment, PaymentRefund
from expenses.models import Expense
from .services import post_invoice_if_needed, post_payment_if_needed, post_expense_if_needed, post_payment_refund_if_needed


@receiver(post_save, sender=Document)
def _post_invoice(sender, instance: Document, created: bool, **kwargs):
    # Post only when invoice is not draft/void
    post_invoice_if_needed(instance)


@receiver(post_save, sender=Payment)
def _post_payment(sender, instance: Payment, created: bool, **kwargs):
    post_payment_if_needed(instance)



@receiver(post_save, sender=PaymentRefund)
def _post_payment_refund(sender, instance: PaymentRefund, created: bool, **kwargs):
    post_payment_refund_if_needed(instance)


@receiver(post_save, sender=Expense)
def _post_expense(sender, instance: Expense, created: bool, **kwargs):
    post_expense_if_needed(instance)
