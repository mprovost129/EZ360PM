from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.utils.paths import get_settings_path


@dataclass
class LocalSettings:
    base_url: str = "http://127.0.0.1:8000"
    sync_enabled: bool = True
    sync_interval_seconds: int = 60
    active_company_id: str = ""


def load_settings(path: Path | None = None) -> LocalSettings:
    p = path or get_settings_path()
    if not p.exists():
        s = LocalSettings()
        save_settings(s, p)
        return s
    data = json.loads(p.read_text(encoding="utf-8") or "{}")
    return LocalSettings(
        base_url=str(data.get("base_url") or "http://127.0.0.1:8000").rstrip("/"),
        sync_enabled=bool(data.get("sync_enabled", True)),
        sync_interval_seconds=int(data.get("sync_interval_seconds", 60)),
        active_company_id=str(data.get("active_company_id", "")),
    )


def save_settings(settings: LocalSettings, path: Path | None = None) -> None:
    p = path or get_settings_path()
    p.write_text(
        json.dumps(
            {
                "base_url": settings.base_url.rstrip("/"),
                "sync_enabled": settings.sync_enabled,
                "sync_interval_seconds": settings.sync_interval_seconds,
                "active_company_id": settings.active_company_id,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
