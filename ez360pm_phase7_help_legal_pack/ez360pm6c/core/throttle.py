from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.core.cache import cache


@dataclass(frozen=True)
class ThrottleResult:
    allowed: bool
    remaining: int
    limit: int
    window_seconds: int


def throttle_key(prefix: str, identifier: str) -> str:
    return f"throttle:{prefix}:{identifier}"


def hit(prefix: str, identifier: str, *, limit: int, window_seconds: int) -> ThrottleResult:
    """
    Simple fixed-window throttle using Django cache.

    - Increments a counter for (prefix, identifier)
    - Blocks if count > limit
    """
    key = throttle_key(prefix, identifier)
    count = cache.get(key)
    if count is None:
        cache.set(key, 1, timeout=window_seconds)
        count = 1
    else:
        try:
            count = int(count) + 1
        except Exception:
            count = 1
        cache.set(key, count, timeout=window_seconds)

    allowed = count <= limit
    remaining = max(0, limit - count)
    return ThrottleResult(allowed=allowed, remaining=remaining, limit=limit, window_seconds=window_seconds)
