# core/services.py
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, List, Dict, Any, Optional

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from timetracking.models import TimeEntry
from .models import Notification

User = get_user_model()


# ============================
# Notifications
# ============================

def notify(
    company: Any,
    recipient: Any,
    text: str,
    *,
    actor: Optional[Any] = None,
    kind: str = Notification.GENERIC,
    url: str = "",
    target: Optional[Any] = None,
) -> Notification:
    """
    Create a single notification. If a target model instance is provided,
    it's linked via GenericForeignKey.
    """
    n = Notification(
        company=company,
        recipient=recipient,
        actor=actor,
        kind=kind,
        text=text[:280],
        url=(url or "")[:500],
    )
    if target is not None:
        ct = ContentType.objects.get_for_model(target, for_concrete_model=False)
        n.target_content_type = ct
        n.target_object_id = getattr(target, "pk", None)
    n.save()
    return n


def notify_many(
    company: Any,
    recipients: Iterable[Any],
    text: str,
    *,
    actor: Optional[Any] = None,
    kind: str = Notification.GENERIC,
    url: str = "",
    target: Optional[Any] = None,
) -> int:
    """
    Bulk-create the same notification for multiple recipients.
    Returns the number of notifications created.
    """
    recipients = list(recipients)
    if not recipients:
        return 0

    ct = oid = None
    if target is not None:
        ct = ContentType.objects.get_for_model(target, for_concrete_model=False)
        oid = getattr(target, "pk", None)

    text = text[:280]
    url = (url or "")[:500]

    objs = [
        Notification(
            company=company,
            recipient=r,
            actor=actor,
            kind=kind,
            text=text,
            url=url,
            target_content_type=ct,
            target_object_id=oid,
        )
        for r in recipients
    ]
    created = Notification.objects.bulk_create(objs)
    return len(created)


def unread_count(company: Any, user: Any) -> int:
    """Return unread count for a user in a company; 0 if unauthenticated/none."""
    if not company or not getattr(user, "is_authenticated", False):
        return 0
    return Notification.objects.for_company_user(company, user).unread().count()  # type: ignore[attr-defined]


def mark_all_read(company: Any, user: Any) -> int:
    """Mark all unread as read; returns rows updated."""
    if not company or not getattr(user, "is_authenticated", False):
        return 0
    return Notification.objects.for_company_user(company, user).unread().update(read_at=timezone.now())  # type: ignore[attr-defined]


# ============================
# Time → Invoice
# ============================

def _round_hours(hours: Decimal, step: Decimal) -> Decimal:
    """
    Round hours to a given step (e.g., 0.25 for quarter-hour).
    Defaults to 0.01 if step <= 0.
    """
    if step <= 0:
        return hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return ((hours / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step).quantize(Decimal("0.01"))


def _parse_rounding(val: str) -> Decimal:
    """Parse a rounding step from string; returns 0 on failure (meaning no step)."""
    try:
        f = Decimal(val)
        return f if f > 0 else Decimal("0")
    except Exception:
        return Decimal("0")


def group_time_entries(
    entries: Iterable[TimeEntry],
    group_by: str,
    rounding_step: Decimal,
) -> List[Dict[str, Any]]:
    """
    Group time entries for invoicing.

    Returns list of dicts:
      { "label": str, "hours": Decimal, "entries": [TimeEntry] }

    group_by options:
      - "day": by entry start date (ISO YYYY-MM-DD)
      - "user": by user email (or user_id fallback)
      - "entry": one bucket per entry
      - "project": by project name (or "Project")
      - other/unknown: single "all" bucket
    """
    buckets: Dict[Any, List[TimeEntry]] = defaultdict(list)
    for t in entries:
        if group_by == "day":
            d = (t.start_time.date() if getattr(t, "start_time", None) else timezone.localdate())
            key = d.isoformat()
        elif group_by == "user":
            key = getattr(getattr(t, "user", None), "email", None) or str(getattr(t, "user_id", ""))
        elif group_by == "entry":
            key = getattr(t, "pk", None)
        elif group_by == "project":
            key = getattr(getattr(t, "project", None), "name", None) or "Project"
        else:
            key = "all"
        buckets[key].append(t)

    out: List[Dict[str, Any]] = []
    for key, rows in buckets.items():
        total = sum((Decimal(str(getattr(r, "hours", 0) or 0)) for r in rows), Decimal("0"))
        total = _round_hours(total, rounding_step)
        out.append({"label": str(key), "hours": total, "entries": rows})

    # Deterministic ordering: by label (ISO/date and strings sort nicely)
    out.sort(key=lambda x: str(x["label"]))
    return out
