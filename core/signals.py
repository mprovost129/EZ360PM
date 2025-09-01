# core/signals.py
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance: User, created: bool, **kwargs) -> None: # type: ignore
    """
    Ensure each new User automatically has a related UserProfile.
    """
    if created:
        UserProfile.objects.get_or_create(user=instance)
