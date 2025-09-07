# accounts/backends.py
from __future__ import annotations

from typing import Any, Optional

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth import get_user_model
from django.http import HttpRequest


class EmailBackend(ModelBackend):
    """
    Authenticate against the custom User model using email instead of username.

    - Accepts both `username` and `email` keyword arguments.
    - Normalizes email to lowercase before lookup.
    - Respects `is_active` via `user_can_authenticate`.
    """

    def authenticate(
        self,
        request: Optional[HttpRequest],
        username: str | None = None,
        password: str | None = None,
        email: str | None = None,
        **kwargs: Any,
    ) -> Optional[AbstractBaseUser]:
        UserModel = get_user_model()

        ident = (email or username or "").strip().lower()
        if not ident or password is None:
            return None

        try:
            user = UserModel.objects.get(email__iexact=ident)
        except UserModel.DoesNotExist:
            # Dummy hash to mitigate timing attacks (same pattern Django uses)
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            # If duplicates ever exist, pick a deterministic one
            user = (
                UserModel.objects.filter(email__iexact=ident)
                .order_by("id")
                .first()
            )
            if not user:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
