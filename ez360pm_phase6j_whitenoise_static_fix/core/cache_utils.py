from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache


def cache_enabled() -> bool:
    return bool(getattr(settings, "EZ360_CACHE_ENABLED", False))


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]


def build_company_request_cache_key(prefix: str, company_id: str, full_path: str) -> str:
    """Stable cache key for per-company, per-request caching."""
    return f"ez360:{prefix}:c{company_id}:{_hash(full_path)}"


@dataclass(frozen=True)
class CacheResult:
    hit: bool
    value: Any


def get_or_set(key: str, ttl_seconds: int, builder: Callable[[], Any]) -> CacheResult:
    if not cache_enabled():
        return CacheResult(hit=False, value=builder())

    val = cache.get(key)
    if val is not None:
        return CacheResult(hit=True, value=val)

    val = builder()
    cache.set(key, val, ttl_seconds)
    return CacheResult(hit=False, value=val)
