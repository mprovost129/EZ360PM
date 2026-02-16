from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from app.auth.token_store import TokenBundle, save_tokens


class ApiError(Exception):
    pass


@dataclass
class ApiClient:
    base_url: str
    tokens: TokenBundle

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self.tokens.access:
            h["Authorization"] = f"Bearer {self.tokens.access}"
        return h

    def post(self, path: str, json_data: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        r = requests.post(url, json=json_data or {}, headers=self._headers(), timeout=timeout)
        if r.status_code >= 400:
            raise ApiError(f"{r.status_code}: {r.text}")
        return r.json()

    def get(self, path: str, params: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        r = requests.get(url, params=params or {}, headers=self._headers(), timeout=timeout)
        if r.status_code >= 400:
            raise ApiError(f"{r.status_code}: {r.text}")
        return r.json()

    def refresh_access_token(self) -> None:
        if not self.tokens.refresh:
            raise ApiError("Missing refresh token.")
        data = self.post("/api/v1/auth/token/refresh/", {"refresh": self.tokens.refresh})
        access = str(data.get("access") or "")
        if not access:
            raise ApiError("Refresh succeeded but returned no access token.")
        self.tokens.access = access
        save_tokens(self.tokens)
