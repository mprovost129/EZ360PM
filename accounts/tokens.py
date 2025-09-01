# accounts/tokens.py
from __future__ import annotations

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import salted_hmac


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """
    Token generator for email verification.

    Based on Django's PasswordResetTokenGenerator but includes the user's
    `is_verified` state so that tokens become invalid once a user is verified.
    """

    def _make_hash_value(self, user, timestamp: int) -> str:  # type: ignore[override]
        # If your User model always has is_verified, this is safe
        verified = getattr(user, "is_verified", False)
        return f"{user.pk}{timestamp}{verified}"


# Singleton instance
email_verification_token = EmailVerificationTokenGenerator()
