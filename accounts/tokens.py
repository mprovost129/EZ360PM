# accounts/tokens.py
from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """
    Token generator for email verification.

    Extends Django's PasswordResetTokenGenerator but incorporates the user's
    `is_verified` flag, so once a user is marked verified, all previously issued
    tokens are invalidated.
    """

    def _make_hash_value(self, user: AbstractBaseUser | Any, timestamp: int) -> str:  # type: ignore[override]
        verified = getattr(user, "is_verified", False)
        return f"{str(user.pk)}{timestamp}{verified}"


# Singleton instance (import and use this directly)
email_verification_token = EmailVerificationTokenGenerator()