from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from companies.models import Company

from .services import ensure_company_subscription


@receiver(post_save, sender=Company)
def create_subscription_for_new_company(sender, instance: Company, created: bool, **kwargs):
    if not created:
        return
    # Initialize a trial subscription record for the new company.
    ensure_company_subscription(instance)
