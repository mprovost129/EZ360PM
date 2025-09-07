# accounts/utils.py
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import AnonymousUser

from .models import UserProfile

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model
    User = get_user_model()  # type: ignore


__all__ = ["get_user_profile"]


def get_user_profile(user: "User") -> UserProfile: # type: ignore
    """
    Ensure and return a profile for the given user.

    - Anonymous users are not supported; caller should guard.
    - Uses get_or_create so it's safe to call repeatedly.
    """
    if isinstance(user, AnonymousUser):
        raise ValueError("get_user_profile() does not support AnonymousUser.")

    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile
