from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils import timezone

from core.email_utils import EmailSpec, send_templated_email


SIGNING_SALT = "accounts.email.verify"
DEFAULT_MAX_AGE_SECONDS = 60 * 60 * 24 * 3  # 3 days


@dataclass(frozen=True)
class VerifyEmailToken:
    user_id: int
    email: str


def build_verify_token(user_id: int, email: str) -> str:
    signer = signing.TimestampSigner(salt=SIGNING_SALT)
    value = f"{user_id}:{email.lower()}"
    return signer.sign(value)


def parse_verify_token(token: str, *, max_age_seconds: int | None = None) -> VerifyEmailToken:
    signer = signing.TimestampSigner(salt=SIGNING_SALT)
    max_age = max_age_seconds or getattr(settings, "ACCOUNTS_VERIFY_EMAIL_MAX_AGE_SECONDS", DEFAULT_MAX_AGE_SECONDS)
    value = signer.unsign(token, max_age=max_age)
    user_id_str, email = value.split(":", 1)
    return VerifyEmailToken(user_id=int(user_id_str), email=email)


def send_verify_email(request, user) -> None:
    token = build_verify_token(user.id, user.email)
    url = request.build_absolute_uri(reverse("accounts:verify_email", kwargs={"token": token}))

    ctx = {
        "site_name": getattr(settings, "SITE_NAME", "EZ360PM"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", "support@ez360pm.com"),
        "user": user,
        "verify_url": url,
        "requested_at": timezone.now(),
    }

    send_templated_email(
        EmailSpec(
            subject="Verify your email",
            to=[user.email],
            context=ctx,
            template_html="emails/verify_email.html",
            template_txt="emails/verify_email.txt",
        ),
        fail_silently=False,
    )
