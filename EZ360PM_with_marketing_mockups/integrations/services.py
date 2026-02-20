from __future__ import annotations

import base64
import json
import hashlib
import os
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional

import requests
from django.conf import settings
from django.urls import reverse
from django.utils import timezone


DROPBOX_AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_ME_URL = "https://api.dropboxapi.com/2/users/get_current_account"
DROPBOX_CREATE_FOLDER_URL = "https://api.dropboxapi.com/2/files/create_folder_v2"
DROPBOX_LIST_SHARED_LINKS_URL = "https://api.dropboxapi.com/2/sharing/list_shared_links"
DROPBOX_GET_METADATA_URL = "https://api.dropboxapi.com/2/files/get_metadata"


@dataclass
class DropboxTokenResult:
    access_token: str
    account_id: str
    token_type: str
    scope: str
    expires_in: Optional[int] = None

def _slugify_part(value: str, max_len: int = 60) -> str:
    value = (value or "").strip()
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    if not value:
        return "item"
    return value[:max_len]


def build_dropbox_project_folder(company, project) -> str:
    """Deterministic folder path for a project's files."""
    company_part = f"{company.id}"
    proj_label = project.project_number or project.name or str(project.id)
    proj_part = _slugify_part(proj_label, max_len=70)
    return f"/EZ360PM/{company_part}/projects/{proj_part}-{project.id}"


def dropbox_is_configured() -> bool:
    return bool(getattr(settings, "DROPBOX_APP_KEY", "")) and bool(getattr(settings, "DROPBOX_APP_SECRET", ""))


def build_redirect_uri(request) -> str:
    explicit = getattr(settings, "DROPBOX_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    return request.build_absolute_uri(reverse("integrations:dropbox_callback"))


def _pkce_verifier() -> str:
    # 64 chars URL-safe
    raw = base64.urlsafe_b64encode(os.urandom(48)).decode("utf-8")
    return raw.rstrip("=")


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def build_authorize_url(request, state: str, verifier: str) -> str:
    challenge = _pkce_challenge(verifier)
    params = {
        "client_id": settings.DROPBOX_APP_KEY,
        "response_type": "code",
        "redirect_uri": build_redirect_uri(request),
        "state": state,
        "token_access_type": "offline",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    qs = "&".join([f"{k}={requests.utils.quote(str(v))}" for k, v in params.items()])
    return f"{DROPBOX_AUTH_URL}?{qs}"


def exchange_code_for_token(request, code: str, verifier: str) -> DropboxTokenResult:
    data = {
        "code": code,
        "grant_type": "authorization_code",
        "client_id": settings.DROPBOX_APP_KEY,
        "client_secret": settings.DROPBOX_APP_SECRET,
        "redirect_uri": build_redirect_uri(request),
        "code_verifier": verifier,
    }
    resp = requests.post(DROPBOX_TOKEN_URL, data=data, timeout=20)
    resp.raise_for_status()
    payload: dict[str, Any] = resp.json()
    return DropboxTokenResult(
        access_token=str(payload.get("access_token", "")),
        account_id=str(payload.get("account_id", "")),
        token_type=str(payload.get("token_type", "")),
        scope=str(payload.get("scope", "")),
        expires_in=int(payload["expires_in"]) if payload.get("expires_in") else None,
    )


def fetch_current_account(access_token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    resp = requests.post(DROPBOX_ME_URL, headers=headers, json={}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def compute_expires_at(expires_in: Optional[int]) -> Optional[timezone.datetime]:
    if not expires_in:
        return None
    return timezone.now() + timedelta(seconds=int(expires_in))


def new_state() -> str:
    return base64.urlsafe_b64encode(os.urandom(24)).decode("utf-8").rstrip("=")


def new_verifier() -> str:
    return _pkce_verifier()


DROPBOX_UPLOAD_URL = "https://content.dropboxapi.com/2/files/upload"
DROPBOX_SHARED_LINK_URL = "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings"




def dropbox_ensure_folder(access_token: str, folder_path: str) -> None:
    """Ensure a folder exists. No-op if it already exists."""
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    resp = requests.post(
        DROPBOX_CREATE_FOLDER_URL,
        headers=headers,
        json={"path": folder_path, "autorename": False},
        timeout=20,
    )
    if resp.status_code == 409:
        # already exists or conflict; treat as ok for v1
        return
    resp.raise_for_status()


def dropbox_list_shared_links(access_token: str, dropbox_path: str) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    resp = requests.post(
        DROPBOX_LIST_SHARED_LINKS_URL,
        headers=headers,
        json={"path": dropbox_path, "direct_only": True},
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    return list(payload.get("links") or [])
def dropbox_upload_bytes(access_token: str, dropbox_path: str, content: bytes) -> dict[str, Any]:
    """Upload bytes to Dropbox and return the API response."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/octet-stream",
        "Dropbox-API-Arg": json.dumps(
            {
                "path": dropbox_path,
                "mode": "add",
                "autorename": True,
                "mute": False,
                "strict_conflict": False,
            }
        ),
    }
    resp = requests.post(DROPBOX_UPLOAD_URL, headers=headers, data=content, timeout=60)
    resp.raise_for_status()
    return resp.json()


def dropbox_create_shared_link(access_token: str, dropbox_path: str) -> str:
    """Create or reuse a shared link for a Dropbox path and return the URL."""
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    resp = requests.post(
        DROPBOX_SHARED_LINK_URL,
        headers=headers,
        json={
            "path": dropbox_path,
            "settings": {
                "requested_visibility": "public",
                "audience": "public",
                "access": "viewer",
            },
        },
        timeout=20,
    )
    if resp.status_code == 409:
        # link may already exist
        try:
            links = dropbox_list_shared_links(access_token, dropbox_path)
            if links:
                return str(links[0].get("url", ""))
        except Exception:
            pass
    resp.raise_for_status()
    payload = resp.json()
    return str(payload.get("url", ""))


# -----------------------------------------------------------------------------
# Bank feeds (scaffold)
# -----------------------------------------------------------------------------


def bank_feeds_is_configured() -> bool:
    """Returns True when Plaid env vars are present.

    This pack intentionally avoids hard dependency on Plaid SDK.
    """

    return bool(getattr(settings, "PLAID_CLIENT_ID", "")) and bool(getattr(settings, "PLAID_SECRET", ""))


def bank_feeds_is_enabled() -> bool:
    return bool(getattr(settings, "PLAID_ENABLED", False))

# --------------------------------------------------------------------------------------
# Plaid bank feeds (no SDK dependency)
# --------------------------------------------------------------------------------------

PLAID_ENV_URLS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}


def _plaid_base_url() -> str:
    env = (getattr(settings, "PLAID_ENV", "") or "sandbox").strip().lower()
    return PLAID_ENV_URLS.get(env, PLAID_ENV_URLS["sandbox"])


def _plaid_headers() -> dict[str, str]:
    return {"Content-Type": "application/json"}


def _plaid_auth_payload() -> dict[str, str]:
    return {
        "client_id": getattr(settings, "PLAID_CLIENT_ID", ""),
        "secret": getattr(settings, "PLAID_SECRET", ""),
    }


def plaid_create_link_token(*, company, user) -> str:
    """Create a Plaid Link token for the given company/user.

    Uses Products: transactions. Add additional products later if needed.
    """
    url = f"{_plaid_base_url()}/link/token/create"
    payload: dict[str, Any] = {
        **_plaid_auth_payload(),
        "client_name": "EZ360PM",
        "language": "en",
        "country_codes": ["US"],
        "user": {
            # Must be unique/stable per user. Use auth user id.
            "client_user_id": str(getattr(user, "id", "")),
        },
        "products": ["transactions"],
        "transactions": {
            # keep modest to reduce initial payload size
            "days_requested": 90,
        },
        # Tie this to the company for internal visibility.
        "client_idempotency_key": f"ez360pm:{company.id}:linktoken:{getattr(user, 'id', '')}",
    }
    resp = requests.post(url, headers=_plaid_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return str(data.get("link_token", ""))


def plaid_exchange_public_token(*, public_token: str) -> dict[str, str]:
    url = f"{_plaid_base_url()}/item/public_token/exchange"
    payload = {**_plaid_auth_payload(), "public_token": public_token}
    resp = requests.post(url, headers=_plaid_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return {
        "access_token": str(data.get("access_token", "")),
        "item_id": str(data.get("item_id", "")),
    }


def plaid_fetch_accounts(*, access_token: str) -> dict[str, Any]:
    url = f"{_plaid_base_url()}/accounts/get"
    payload = {**_plaid_auth_payload(), "access_token": access_token}
    resp = requests.post(url, headers=_plaid_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def plaid_transactions_sync(*, access_token: str, cursor: str | None = None) -> dict[str, Any]:
    """Incremental sync of transactions.

    Returns a dict containing added/modified/removed plus next_cursor + has_more.
    """
    url = f"{_plaid_base_url()}/transactions/sync"
    payload: dict[str, Any] = {**_plaid_auth_payload(), "access_token": access_token}
    if cursor:
        payload["cursor"] = cursor
    resp = requests.post(url, headers=_plaid_headers(), json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def suggest_existing_expense_for_tx(*, company, tx):
    """Return (expense, score) for a potential duplicate match.

    This is intentionally conservative so we do not auto-link incorrectly.
    The suggestion is used only in the Bank Review Queue UI.

    Heuristic:
    - same company
    - same total cents
    - expense date within +/- 1 day of posted_date
    - merchant name matches (case-insensitive equals or containment)

    Score is 0..100. 0 means no suggestion.
    """

    try:
        from expenses.models import Expense
    except Exception:
        return (None, 0)

    if not company or not tx:
        return (None, 0)

    if getattr(tx, "linked_expense_id", None):
        return (None, 0)
    if int(getattr(tx, "amount_cents", 0) or 0) <= 0:
        return (None, 0)

    posted = getattr(tx, "posted_date", None)
    if not posted:
        return (None, 0)

    tx_name = (getattr(tx, "suggested_merchant_name", "") or getattr(tx, "name", "") or "").strip().lower()
    if not tx_name:
        return (None, 0)

    date_min = posted - timedelta(days=1)
    date_max = posted + timedelta(days=1)

    qs = (
        Expense.objects.filter(company=company, total_cents=int(tx.amount_cents), date__gte=date_min, date__lte=date_max)
        .select_related("merchant")
        .order_by("-id")
    )

    best = None
    best_score = 0
    for exp in qs[:25]:
        m = (getattr(getattr(exp, "merchant", None), "name", "") or "").strip().lower()
        if not m:
            continue
        if m == tx_name:
            score = 95
        elif m in tx_name or tx_name in m:
            score = 75
        else:
            continue

        if exp.date == posted:
            score = min(100, score + 5)

        if score > best_score:
            best = exp
            best_score = score
            if best_score >= 95:
                break

    return (best, best_score)
