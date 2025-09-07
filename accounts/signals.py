# accounts/signals.py
from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender: type[User], instance: User, created: bool, **kwargs: Any) -> None: # type: ignore
    """
    Ensure each new User automatically has a related UserProfile.

    This will only run on initial creation. If you want to also
    touch `updated_at` on profile when a user saves, add another
    receiver for `post_save` without the `created` check.
    """
    if created:
        UserProfile.objects.get_or_create(user=instance)

