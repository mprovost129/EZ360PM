from __future__ import annotations

import os
from pathlib import Path


def get_app_dir() -> Path:
    """
    Windows-friendly per-user app directory.

    Uses %APPDATA%\EZ360PMDesktop by default.
    """
    base = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA") or str(Path.home())
    p = Path(base) / "EZ360PMDesktop"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_data_dir() -> Path:
    p = get_app_dir() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_db_path() -> Path:
    return get_data_dir() / "ez360pm.sqlite3"


def get_token_path() -> Path:
    return get_data_dir() / "tokens.json"


def get_settings_path() -> Path:
    return get_data_dir() / "settings.json"
