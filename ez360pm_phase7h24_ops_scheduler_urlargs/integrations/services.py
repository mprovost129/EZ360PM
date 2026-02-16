from __future__ import annotations

import base64
import json
import hashlib
import os
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
