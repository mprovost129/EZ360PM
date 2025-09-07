from __future__ import annotations
import json
from datetime import datetime, timedelta
from typing import TypedDict

CONSENT_COOKIE = "cookie_consent"
CONSENT_MAX_AGE = 365 * 24 * 60 * 60  # 1 year

class Consent(TypedDict):
    essential: bool
    analytics: bool
    marketing: bool
    ts: str

def get_cookie_consent(request) -> Consent:
    try:
        data = json.loads(request.COOKIES.get(CONSENT_COOKIE, "") or "{}")
    except json.JSONDecodeError:
        data = {}
    return {
        "essential": True,  # always on
        "analytics": bool(data.get("analytics", False)),
        "marketing": bool(data.get("marketing", False)),
        "ts": str(data.get("ts", "")),
    }

def set_consent_cookie(response, consent: Consent, *, secure: bool = True):
    payload = json.dumps(consent, separators=(",", ":"))
    # Use `Secure` + `HttpOnly=False` (JS may need to read analytic flags; flip if not)
    response.set_cookie(
        CONSENT_COOKIE,
        payload,
        max_age=CONSENT_MAX_AGE,
        samesite="Lax",
        secure=secure,
    )