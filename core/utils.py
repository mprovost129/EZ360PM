# core/utils.py
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta
from typing import Optional, Tuple

from django.conf import settings
from django.utils import timezone
from datetime import datetime, timedelta, timezone as dt_tz
from zoneinfo import ZoneInfo, available_timezones

from company.models import Company, CompanyMember


ACTIVE_COMPANY_SESSION_KEY = "active_company_id"

__all__ = [
    "parse_date",
    "default_range_last_30",
    "add_months",
    "advance_schedule",
    "week_range",
    "combine_midday",
    "get_user_membership",
    "user_has_active_subscription",
    # new helpers (optional)
    "normalize_date_range",
    "iso_today",
]


# ---------------------------------------------------------------------
# Date utilities
# ---------------------------------------------------------------------

def parse_date(value: Optional[str]) -> Optional[date]:
    """
    Parse ISO-like dates (YYYY-MM-DD or ISO datetime). Return None on failure.
    Accepts full ISO strings and extracts the date portion; tolerates trailing 'Z'.
    """
    if not value:
        return None

    # Try datetime.fromisoformat first (handles 'YYYY-MM-DD' as well)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.date()
    except Exception:
        pass

    # Fallback strict date
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def default_range_last_30() -> Tuple[date, date]:
    """
    (start, end) covering the last 30 days inclusive, ending today.
    Example: if today is the 31st, start is the 2nd (i.e., 29 days before today).
    """
    today = timezone.localdate()
    return today - timedelta(days=29), today  # inclusive 30-day window


def add_months(d: date, months: int) -> date:
    """Add N calendar months to a date, clamping the day if needed."""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


def advance_schedule(d: date, freq: str) -> date:
    """
    Move date forward based on a string frequency.
    Supported: daily, weekly, biweekly, monthly, quarterly, yearly.
    """
    f = (freq or "").lower()
    if f == "daily":
        return d + timedelta(days=1)
    if f in {"weekly"}:
        return d + timedelta(weeks=1)
    if f in {"biweekly", "fortnightly"}:
        return d + timedelta(weeks=2)
    if f == "monthly":
        return add_months(d, 1)
    if f == "quarterly":
        return add_months(d, 3)
    if f == "yearly":
        return add_months(d, 12)
    return d


def week_range(d: date) -> Tuple[date, date]:
    """Return (monday, sunday) for the week containing d."""
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def combine_midday(d: date) -> datetime:
    """
    Combine a date with 12:00 local time.
    Returns TZ-aware datetime when USE_TZ is True.
    """
    naive = datetime.combine(d, time(12, 0))
    if getattr(settings, "USE_TZ", True):
        # Always return aware when USE_TZ is enabled
        return timezone.make_aware(naive, timezone.get_current_timezone())
    return naive


def normalize_date_range(start: Optional[date], end: Optional[date]) -> Tuple[date, date]:
    """
    Ensure (start, end) are present and ordered, defaulting to last 30 days if missing.
    If only one is provided, fills the other to create a sensible 30-day window.
    """
    if start and end:
        return (start, end) if start <= end else (end, start)

    if start and not end:
        # 30-day inclusive window ending 29 days after start (or today, whichever is earlier)
        candidate_end = start + timedelta(days=29)
        today = timezone.localdate()
        return start, (candidate_end if candidate_end <= today else today)

    if end and not start:
        return end - timedelta(days=29), end

    return default_range_last_30()


def iso_today() -> str:
    """Return today's local date in ISO format (YYYY-MM-DD)."""
    return timezone.localdate().isoformat()


# ---------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------

def get_user_membership(user, company: Optional[Company]) -> Optional[CompanyMember]:
    """Return the CompanyMember row tying user to company, if any."""
    if not company or not getattr(user, "is_authenticated", False):
        return None
    return CompanyMember.objects.filter(company=company, user=user).first()


def user_has_active_subscription(company) -> bool:
    """
    Lightweight check that the attached subscription object is active/trialing.
    This avoids coupling to a billing app.
    """
    sub = getattr(company, "subscription", None)
    status = getattr(sub, "status", "") if sub else ""
    return bool(sub) and status in {"active", "trialing"}


def build_timezone_choices():
    now = datetime.now(dt_tz.utc)
    regions = ("Africa/", "America/", "Antarctica/", "Asia/", "Atlantic/",
               "Australia/", "Europe/", "Indian/", "Pacific/")

    tzs = [tz for tz in available_timezones() if tz.startswith(regions)]

    def offset_seconds(tzname: str) -> int:
        try:
            off = now.astimezone(ZoneInfo(tzname)).utcoffset() or timedelta(0)
        except Exception:
            return 0
        return int(off.total_seconds())

    def label(tzname: str) -> str:
        off = now.astimezone(ZoneInfo(tzname)).utcoffset() or timedelta(0)
        total = int(off.total_seconds())
        sign = "+" if total >= 0 else "-"
        hh = abs(total) // 3600
        mm = (abs(total) % 3600) // 60
        return f"(UTC{sign}{hh:02d}:{mm:02d}) {tzname}"

    tzs.sort(key=lambda z: (offset_seconds(z), z))
    return [(z, label(z)) for z in tzs]

TIMEZONE_CHOICES = build_timezone_choices()

US_STATE_CHOICES = [
    ("", "— Select —"),
    ("AL","Alabama"), ("AK","Alaska"), ("AZ","Arizona"), ("AR","Arkansas"),
    ("CA","California"), ("CO","Colorado"), ("CT","Connecticut"), ("DE","Delaware"),
    ("DC","District of Columbia"), ("FL","Florida"), ("GA","Georgia"), ("HI","Hawaii"),
    ("ID","Idaho"), ("IL","Illinois"), ("IN","Indiana"), ("IA","Iowa"),
    ("KS","Kansas"), ("KY","Kentucky"), ("LA","Louisiana"), ("ME","Maine"),
    ("MD","Maryland"), ("MA","Massachusetts"), ("MI","Michigan"), ("MN","Minnesota"),
    ("MS","Mississippi"), ("MO","Missouri"), ("MT","Montana"), ("NE","Nebraska"),
    ("NV","Nevada"), ("NH","New Hampshire"), ("NJ","New Jersey"), ("NM","New Mexico"),
    ("NY","New York"), ("NC","North Carolina"), ("ND","North Dakota"), ("OH","Ohio"),
    ("OK","Oklahoma"), ("OR","Oregon"), ("PA","Pennsylvania"), ("RI","Rhode Island"),
    ("SC","South Carolina"), ("SD","South Dakota"), ("TN","Tennessee"),
    ("TX","Texas"), ("UT","Utah"), ("VT","Vermont"), ("VA","Virginia"),
    ("WA","Washington"), ("WV","West Virginia"), ("WI","Wisconsin"), ("WY","Wyoming"),
]