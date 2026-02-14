from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from django.conf import settings


@dataclass(frozen=True)
class RecaptchaResult:
    ok: bool
    score: float
    action: str
    hostname: str
    error_codes: Tuple[str, ...]


def recaptcha_is_enabled() -> bool:
    return bool(getattr(settings, "RECAPTCHA_ENABLED", False)) and bool(getattr(settings, "RECAPTCHA_SECRET_KEY", ""))


def verify_recaptcha(token: str, remoteip: str | None = None) -> RecaptchaResult:
    """
    Verify reCAPTCHA v3 token against Google.

    Returns a RecaptchaResult. If reCAPTCHA is disabled, this returns ok=True.
    """
    if not recaptcha_is_enabled():
        return RecaptchaResult(ok=True, score=1.0, action="", hostname="", error_codes=())

    token = (token or "").strip()
    if not token:
        return RecaptchaResult(ok=False, score=0.0, action="", hostname="", error_codes=("missing-input-response",))

    data = {
        "secret": getattr(settings, "RECAPTCHA_SECRET_KEY", ""),
        "response": token,
    }
    if remoteip:
        data["remoteip"] = remoteip

    payload = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        "https://www.google.com/recaptcha/api/siteverify",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            raw = resp.read().decode("utf-8")
            obj: Dict[str, Any] = json.loads(raw)
    except Exception:
        return RecaptchaResult(ok=False, score=0.0, action="", hostname="", error_codes=("verify-error",))

    ok = bool(obj.get("success", False))
    score = float(obj.get("score") or 0.0)
    action = str(obj.get("action") or "")
    hostname = str(obj.get("hostname") or "")
    error_codes = tuple(obj.get("error-codes") or [])

    return RecaptchaResult(ok=ok, score=score, action=action, hostname=hostname, error_codes=error_codes)


def passes_policy(result: RecaptchaResult, expected_action: str) -> bool:
    """
    Enforce minimum score + expected action match.
    """
    if not recaptcha_is_enabled():
        return True

    min_score = float(getattr(settings, "RECAPTCHA_MIN_SCORE", 0.5))
    expected_action = (expected_action or "").strip()

    if not result.ok:
        return False
    if expected_action and result.action and result.action != expected_action:
        return False
    return result.score >= min_score
