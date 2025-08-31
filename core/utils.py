# core/utils.py
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta
from typing import Optional, Sequence

from django.http import HttpRequest
from django.utils import timezone
from django.db.models import Max, Q
from typing import TypedDict

from .models import (
    Company,
    CompanyMember,
    Estimate,
    Invoice,
    Project,
    UserProfile,
)

ACTIVE_COMPANY_SESSION_KEY = "active_company_id"


# ---------------------------------------------------------------------
# Company selection / roles
# ---------------------------------------------------------------------
def get_user_companies(user) -> "Company.objects.none.__class__ | Sequence[Company]": # type: ignore
    """
    Returns all companies the user owns OR is a member of.
    Anonymous users get an empty queryset.
    """
    if not getattr(user, "is_authenticated", False):
        return Company.objects.none()
    owns = Company.objects.filter(owner=user)
    member_of = Company.objects.filter(members__user=user)
    return (owns | member_of).distinct()


def get_active_company(request: HttpRequest) -> Optional[Company]:
    """
    Resolve the active company for this request, in order:
      1) session-selected company,
      2) first company the user owns or belongs to.
    Returns None for anonymous users.
    """
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return None

    cid = request.session.get(ACTIVE_COMPANY_SESSION_KEY)
    if cid:
        try:
            return Company.objects.get(id=cid)
        except Company.DoesNotExist:
            # Session may be stale; fall through to membership scan
            pass

    companies = get_user_companies(user)
    return companies.first() if companies else None # type: ignore


def set_active_company(request: HttpRequest, company: Company) -> None:
    """Stores the active company id in session (no membership check here)."""
    request.session[ACTIVE_COMPANY_SESSION_KEY] = int(company.id)  # type: ignore[arg-type]


def user_role_in_company(user, company: Company) -> Optional[str]:
    """Returns 'owner' | 'admin' | 'member' | None."""
    if not getattr(user, "is_authenticated", False) or not company:
        return None
    if company.owner_id == getattr(user, "id", None): # type: ignore
        return CompanyMember.OWNER
    m = CompanyMember.objects.filter(company=company, user=user).only("role").first()
    return m.role if m else None


def require_company_admin(user, company: Optional[Company]) -> bool:
    """
    True if the user is owner/admin for the company.
    Treats Django staff as admin for convenience.
    """
    if not company or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False):
        return True
    role = user_role_in_company(user, company)
    return role in {CompanyMember.OWNER, CompanyMember.ADMIN}


# ---------------------------------------------------------------------
# Number generators
# ---------------------------------------------------------------------
def generate_invoice_number(company: Company) -> str:
    """
    Format: INV-YYYYMM-#### (per company, per month).
    Chooses the next sequence by inspecting the latest existing number
    for the current month. Safe for typical usage; wrap in a transaction
    if you expect heavy concurrency.
    """
    prefix = timezone.now().strftime("INV-%Y%m")
    last = (
        Invoice.objects
        .filter(company=company, number__startswith=prefix)
        .order_by("number")
        .last()
    )
    if not last:
        seq = 1
    else:
        try:
            seq = int(str(last.number).split("-")[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}-{seq:04d}"


def generate_estimate_number(company: Company) -> str:
    """Format: EST-YYYYMM-#### (per company, per month)."""
    prefix = timezone.now().strftime("EST-%Y%m")
    last = (
        Estimate.objects
        .filter(company=company, number__startswith=prefix)
        .order_by("number")
        .last()
    )
    if not last:
        seq = 1
    else:
        try:
            seq = int(str(last.number).split("-")[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}-{seq:04d}"


def generate_project_number(company: Company) -> str:
    """
    Simple per-company sequence like 0001, 0002, ...
    Uses count as a fallback when prior numbers are non-numeric.
    """
    # Try to find the highest fully-numeric number first
    nums = (
        Project.objects
        .filter(company=company)
        .exclude(number__isnull=True)
        .exclude(number__exact="")
        .values_list("number", flat=True)
    )
    max_num = 0
    for n in nums:
        s = str(n).strip()
        if s.isdigit():
            try:
                max_num = max(max_num, int(s))
            except Exception:
                pass

    if max_num == 0:
        # Fallback to count-based sequence
        max_num = Project.objects.filter(company=company).count()

    return f"{max_num + 1:04d}"


# ---------------------------------------------------------------------
# Date utilities
# ---------------------------------------------------------------------
def parse_date(value: Optional[str]) -> Optional[date]:
    """Parses ISO-like dates (YYYY-MM-DD). Returns None on failure."""
    if not value:
        return None
    try:
        # Allow full ISO strings (date or datetime)
        dt = datetime.fromisoformat(value)
        return dt.date()
    except Exception:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except Exception:
            return None


def default_range_last_30() -> tuple[date, date]:
    """(start, end) covering the last 30 days inclusive, ending today."""
    today = timezone.now().date()
    return today - timedelta(days=30), today


def add_months(d: date, months: int) -> date:
    """Add N calendar months to a date, clamping the day if needed."""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


def advance_schedule(d: date, freq: str) -> date:
    """Move date forward based on a string frequency."""
    if freq == "weekly":
        return d + timedelta(weeks=1)
    if freq == "monthly":
        return add_months(d, 1)
    if freq == "quarterly":
        return add_months(d, 3)
    if freq == "yearly":
        return add_months(d, 12)
    return d


def week_range(d: date) -> tuple[date, date]:
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
    if timezone.is_naive(naive):
        try:
            return timezone.make_aware(naive, timezone.get_current_timezone())
        except Exception:
            # As a last resort, return naive; better than failing.
            return naive
    return naive


# ---------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------
def get_user_profile(user) -> UserProfile:
    """
    Ensures a profile exists for the user and returns it.
    Anonymous users are not supported; call sites should guard.
    """
    # If you ever allow anonymous here, return a dummy profile object
    # or None. For now, keep it strict to surface integration mistakes.
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def get_user_membership(user, company: Optional[Company]) -> Optional[CompanyMember]:
    if not company or not getattr(user, "is_authenticated", False):
        return None
    return CompanyMember.objects.filter(company=company, user=user).first()


def user_has_active_subscription(company) -> bool:
    sub = getattr(company, "subscription", None)
    status = getattr(sub, "status", "") if sub else ""
    return bool(sub) and status in {"active", "trialing"}

class OnboardingStatus(TypedDict):
    has_company: bool
    has_client: bool
    has_project: bool
    has_activity: bool  # time or expense
    has_invoice: bool
    is_subscribed: bool
    complete: bool

def get_onboarding_status(user, company) -> OnboardingStatus:
    """
    No migrations required. Computes a simple checklist using current DB state.
    """
    from .models import Company, CompanyMember, Client, Project, TimeEntry, Expense, Invoice
    from .utils import user_has_active_subscription  # you already have this

    # Find *some* company the user belongs to if none active yet
    if not company:
        owned = Company.objects.filter(owner=user).first()
        if owned:
            company = owned
        else:
            member_company_id = (
                CompanyMember.objects
                .filter(user=user)
                .values_list("company_id", flat=True)
                .first()
            )
            if member_company_id:
                company = Company.objects.filter(id=member_company_id).first()

    has_company = bool(company)

    # Counts scoped to active company if available
    if company:
        has_client = Client.objects.filter(company=company).exists()
        has_project = Project.objects.filter(company=company).exists()
        has_time = TimeEntry.objects.filter(project__company=company).exists()
        has_expense = Expense.objects.filter(company=company).exists()
        has_activity = has_time or has_expense
        has_invoice = Invoice.objects.filter(company=company).exists()
        is_subscribed = user_has_active_subscription(company)
    else:
        has_client = has_project = has_activity = has_invoice = False
        is_subscribed = False

    complete = has_company and has_client and has_project and has_activity and has_invoice

    return {
        "has_company": has_company,
        "has_client": has_client,
        "has_project": has_project,
        "has_activity": has_activity,
        "has_invoice": has_invoice,
        "is_subscribed": is_subscribed,
        "complete": complete,
    }