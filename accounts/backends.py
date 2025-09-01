# accounts/backends.py
from __future__ import annotations

from typing import Optional

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.http import HttpRequest

User = get_user_model()


class EmailBackend(ModelBackend):
    """
    Authenticate against the custom User model using email instead of username.
    """

    def authenticate(
        self,
        request: Optional[HttpRequest],
        username: str | None = None,
        password: str | None = None,
        email: str | None = None,
        **kwargs,
    ) -> Optional[User]: # type: ignore
        if email is None:
            # Some auth flows pass `username` instead of `email`
            email = username
        if email is None or password is None:
            return None

        # Normalize email
        email = email.strip().lower()

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
