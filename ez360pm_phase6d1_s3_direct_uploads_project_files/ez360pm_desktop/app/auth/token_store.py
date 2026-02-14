from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.utils.paths import get_token_path


@dataclass
class TokenBundle:
    access: str = ""
    refresh: str = ""
    user_id: str = ""
    username: str = ""


def load_tokens(path: Path | None = None) -> TokenBundle:
    p = path or get_token_path()
    if not p.exists():
        return TokenBundle()
    try:
        data = json.loads(p.read_text(encoding="utf-8") or "{}")
        return TokenBundle(
            access=str(data.get("access", "")),
            refresh=str(data.get("refresh", "")),
            user_id=str(data.get("user_id", "")),
            username=str(data.get("username", "")),
        )
    except Exception:
        return TokenBundle()


def save_tokens(tokens: TokenBundle, path: Path | None = None) -> None:
    p = path or get_token_path()
    p.write_text(
        json.dumps(
            {
                "access": tokens.access,
                "refresh": tokens.refresh,
                "user_id": tokens.user_id,
                "username": tokens.username,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def clear_tokens(path: Path | None = None) -> None:
    save_tokens(TokenBundle(), path)
