from __future__ import annotations

import base64
import hmac
import hashlib
import secrets
import time
from urllib.parse import quote

from django.conf import settings


DEFAULT_STEP_SECONDS = 30
DEFAULT_DIGITS = 6


def generate_base32_secret(nbytes: int = 20) -> str:
    # 20 bytes -> 32 base32 chars (approx). Strip padding for nice display.
    raw = secrets.token_bytes(nbytes)
    return base64.b32encode(raw).decode("utf-8").rstrip("=")


def _totp_counter(ts: int, step: int = DEFAULT_STEP_SECONDS) -> int:
    return int(ts // step)


def totp_code(secret_base32: str, ts: int | None = None, digits: int = DEFAULT_DIGITS) -> str:
    if ts is None:
        ts = int(time.time())

    # base32 decode needs padding
    padding = "=" * ((8 - (len(secret_base32) % 8)) % 8)
    key = base64.b32decode((secret_base32 + padding).encode("utf-8"), casefold=True)

    counter = _totp_counter(ts)
    msg = counter.to_bytes(8, "big")

    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    code = str(code_int % (10 ** digits)).zfill(digits)
    return code


def verify_totp(secret_base32: str, code: str, window: int = 1, digits: int = DEFAULT_DIGITS) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != digits:
        return False

    now = int(time.time())
    for w in range(-window, window + 1):
        if totp_code(secret_base32, ts=now + (w * DEFAULT_STEP_SECONDS), digits=digits) == code:
            return True
    return False


def build_otpauth_url(email: str, secret_base32: str) -> str:
    issuer = getattr(settings, "TWO_FACTOR_ISSUER", "EZ360PM")
    label = f"{issuer}:{email}"
    # RFC: otpauth://totp/label?secret=...&issuer=...
    return f"otpauth://totp/{quote(label)}?secret={secret_base32}&issuer={quote(issuer)}"
