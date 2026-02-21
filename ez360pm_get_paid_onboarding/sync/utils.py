from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Tuple

from django.db import models, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = parse_datetime(value)
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone=timezone.utc)
    return dt


def model_to_sync_dict(obj: models.Model) -> Dict[str, Any]:
    """Serialize a SyncModel instance into a JSON-friendly dict."""

    data: Dict[str, Any] = {
        "id": str(obj.pk),
        "revision": int(getattr(obj, "revision", 0) or 0),
        "updated_at": getattr(obj, "updated_at", None).isoformat() if getattr(obj, "updated_at", None) else None,
        "deleted_at": getattr(obj, "deleted_at", None).isoformat() if getattr(obj, "deleted_at", None) else None,
        "fields": {},
    }

    for field in obj._meta.fields:
        name = field.name
        if name in {"id", "created_at", "updated_at", "revision", "deleted_at", "updated_by_user", "updated_by_device"}:
            continue
        if isinstance(field, models.ForeignKey):
            data["fields"][name] = str(getattr(obj, f"{name}_id") or "") or None
        else:
            value = getattr(obj, name)
            if isinstance(value, datetime):
                data["fields"][name] = value.isoformat()
            else:
                data["fields"][name] = value

    return data


def _coerce_field_value(field: models.Field, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(field, models.DateTimeField):
        if isinstance(value, str):
            return parse_iso_datetime(value)
        return value
    if isinstance(field, models.DateField):
        if isinstance(value, str):
            # YYYY-MM-DD
            try:
                return datetime.fromisoformat(value).date()
            except Exception:
                return None
        return value
    if isinstance(field, models.BooleanField):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return value


@transaction.atomic
def apply_lww_change(
    *,
    obj: models.Model,
    fields: Dict[str, Any],
    client_updated_at: datetime | None,
    server_now: datetime,
    updated_by_user_id: Any | None,
    updated_by_device: str | None,
) -> Tuple[models.Model, bool]:
    """Apply change if it wins LWW.

    Returns: (obj, applied)
    """

    server_updated_at = getattr(obj, "updated_at", None)
    if client_updated_at and server_updated_at and client_updated_at <= server_updated_at:
        return obj, False

    # apply
    field_map = {f.name: f for f in obj._meta.fields}
    for name, value in fields.items():
        if name not in field_map:
            continue
        field = field_map[name]
        if name in {"id", "created_at", "updated_at", "revision", "deleted_at", "updated_by_user", "updated_by_device"}:
            continue
        if isinstance(field, models.ForeignKey):
            setattr(obj, f"{name}_id", value or None)
        else:
            setattr(obj, name, _coerce_field_value(field, value))

    # bump revision, stamp updated_at
    if hasattr(obj, "revision"):
        obj.revision = int(getattr(obj, "revision", 0) or 0) + 1
    if hasattr(obj, "updated_at"):
        obj.updated_at = server_now
    if hasattr(obj, "updated_by_user_id"):
        obj.updated_by_user_id = updated_by_user_id
    if hasattr(obj, "updated_by_device"):
        obj.updated_by_device = updated_by_device

    obj.save()
    return obj, True