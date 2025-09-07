# company/utils.py
from __future__ import annotations

from typing import Optional, TypedDict

from django.db.models.query import QuerySet
from django.http import HttpRequest

from clients.models import Client
from company.models import Company, CompanyMember
from core.decorators import user_has_active_subscription
from invoices.models import Invoice
from projects.models import Project
from timetracking.models import TimeEntry

ACTIVE_COMPANY_SESSION_KEY = "active_company_id"
_REQUEST_CACHE_ATTR = "_active_company_cache"

__all__ = [
    "get_user_companies",
    "get_active_company",
    "set_active_company",
    "clear_active_company",
    "user_has_company_access",
    "user_role_in_company",
    "require_company_admin",
    "OnboardingStatus",
    "get_onboarding_status",
]


# -----------------------------
# Company access helpers
# -----------------------------
def get_user_companies(user) -> QuerySet[Company]:
    """
    Return all Companies the user owns or is a member of.
    Anonymous users get an empty queryset.
    """
    if not getattr(user, "is_authenticated", False):
        return Company.objects.none()

    owns = Company.objects.filter(owner=user)
    member_of = Company.objects.filter(members__user=user)
    # Combine and dedupe; useful to have owner eager-loaded for display
    return (owns | member_of).select_related("owner").distinct()


def user_has_company_access(user, company: Company | None) -> bool:
    """True if user owns or is a member of the company."""
    if not company or not getattr(user, "is_authenticated", False):
        return False
    if company.owner_id == getattr(user, "id", None):  # type: ignore[attr-defined]
        return True
    return CompanyMember.objects.filter(company=company, user=user).exists()


def get_active_company(request: HttpRequest) -> Optional[Company]:
    """
    Resolve the active company for this request, in order:
      1) Session-selected company (only if user has access),
      2) First company the user owns or belongs to.
    Caches the result on the request to avoid repeated queries.
    Returns None for anonymous users.
    """
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return None

    # Per-request memoization
    cached = getattr(request, _REQUEST_CACHE_ATTR, None)
    if isinstance(cached, Company) or cached is None:
        if cached is not None:
            return cached

    # Try session choice, but verify access
    cid = request.session.get(ACTIVE_COMPANY_SESSION_KEY)
    if cid:
        try:
            selected = Company.objects.get(id=cid)
            if user_has_company_access(user, selected):
                setattr(request, _REQUEST_CACHE_ATTR, selected)
                return selected
        except Company.DoesNotExist:
            pass  # stale session; fall through

    # Fallback to first accessible
    companies = get_user_companies(user)
    company = companies.first() if companies.exists() else None
    setattr(request, _REQUEST_CACHE_ATTR, company)
    # Also normalize session if we found a different accessible company
    if company:
        request.session[ACTIVE_COMPANY_SESSION_KEY] = int(company.id)  # type: ignore[arg-type]
    else:
        request.session.pop(ACTIVE_COMPANY_SESSION_KEY, None)
    return company


def set_active_company(request: HttpRequest, company: Company, *, enforce_access: bool = True) -> bool:
    """
    Store the active company ID in session (with optional access enforcement).
    Returns True if set, False if denied.
    """
    if enforce_access and not user_has_company_access(request.user, company):
        return False
    request.session[ACTIVE_COMPANY_SESSION_KEY] = int(company.id)  # type: ignore[arg-type]
    setattr(request, _REQUEST_CACHE_ATTR, company)
    return True


def clear_active_company(request: HttpRequest) -> None:
    """Remove any cached/selected active company from request + session."""
    request.session.pop(ACTIVE_COMPANY_SESSION_KEY, None)
    if hasattr(request, _REQUEST_CACHE_ATTR):
        delattr(request, _REQUEST_CACHE_ATTR)


def user_role_in_company(user, company: Company) -> Optional[str]:
    """Return 'owner' | 'admin' | 'member' | None."""
    if not getattr(user, "is_authenticated", False) or not company:
        return None
    if company.owner_id == getattr(user, "id", None):  # type: ignore[attr-defined]
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


# -----------------------------
# Onboarding
# -----------------------------
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
    Computes a simple onboarding checklist using current DB state.
    No migrations required.
    """
    from expenses.models import Expense  # local import to avoid cycles

    # Prefer provided company; else pick one the user owns; else first membership
    if not company:
        company = Company.objects.filter(owner=user).first()
        if not company:
            cid = (
                CompanyMember.objects
                .filter(user=user)
                .values_list("company_id", flat=True)
                .first()
            )
            if cid:
                company = Company.objects.filter(id=cid).first()

    has_company = bool(company)

    if not company:
        return {
            "has_company": False,
            "has_client": False,
            "has_project": False,
            "has_activity": False,
            "has_invoice": False,
            "is_subscribed": False,
            "complete": False,
        }

    # Counts scoped to active company
    has_client = Client.objects.filter(company=company).exists()
    has_project = Project.objects.filter(company=company).exists()
    has_time = TimeEntry.objects.filter(project__company=company).exists()
    has_expense = Expense.objects.filter(company=company).exists()
    has_activity = has_time or has_expense
    has_invoice = Invoice.objects.filter(company=company).exists()
    is_subscribed = user_has_active_subscription(company)

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
