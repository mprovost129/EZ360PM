from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import AccountLockout


LOCK_THRESHOLDS = [
    (5, timedelta(minutes=5)),
    (10, timedelta(hours=1)),
    (20, timedelta(hours=24)),
]


@dataclass(frozen=True)
class LockoutStatus:
    is_locked: bool
    failed_count: int
    locked_until: timezone.datetime | None


def normalize_identifier(raw: str) -> str:
    return (raw or "").strip().lower()[:254]


def get_status(identifier: str) -> LockoutStatus:
    ident = normalize_identifier(identifier)
    if not ident:
        return LockoutStatus(False, 0, None)
    row = AccountLockout.objects.filter(identifier=ident).first()
    if not row:
        return LockoutStatus(False, 0, None)
    return LockoutStatus(row.is_locked(), int(row.failed_count), row.locked_until)


@transaction.atomic
def record_failure(identifier: str) -> LockoutStatus:
    ident = normalize_identifier(identifier)
    if not ident:
        return LockoutStatus(False, 0, None)

    row, _ = AccountLockout.objects.select_for_update().get_or_create(identifier=ident)
    row.failed_count = int(row.failed_count or 0) + 1
    row.last_failed_at = timezone.now()

    # determine lock duration
    lock_for = None
    for threshold, duration in LOCK_THRESHOLDS:
        if row.failed_count >= threshold:
            lock_for = duration
    if lock_for is not None:
        row.locked_until = timezone.now() + lock_for

    row.save(update_fields=["failed_count", "last_failed_at", "locked_until", "updated_at"])
    return LockoutStatus(row.is_locked(), int(row.failed_count), row.locked_until)


@transaction.atomic
def clear(identifier: str) -> None:
    ident = normalize_identifier(identifier)
    if not ident:
        return
    row = AccountLockout.objects.select_for_update().filter(identifier=ident).first()
    if not row:
        return
    row.clear()


@transaction.atomic
def clear_for_user_email(email: str) -> None:
    clear(email)
