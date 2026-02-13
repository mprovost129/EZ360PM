from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.http import HttpRequest

from core.support_mode import get_support_mode

from .models import Company, EmployeeProfile


ACTIVE_COMPANY_SESSION_KEY = "active_company_id"


def get_active_company_id(request: HttpRequest) -> str:
    return str(request.session.get(ACTIVE_COMPANY_SESSION_KEY, "") or "")


def set_active_company_id(request: HttpRequest, company_id: str) -> None:
    request.session[ACTIVE_COMPANY_SESSION_KEY] = str(company_id)


def clear_active_company_id(request: HttpRequest) -> None:
    request.session.pop(ACTIVE_COMPANY_SESSION_KEY, None)


def user_companies_qs(user) -> "CompanyQuerySet":
    return Company.objects.filter(employees__user=user, employees__deleted_at__isnull=True).distinct()


def ensure_active_company_for_user(request: HttpRequest) -> bool:
    """
    Ensures the session has an active company the current user belongs to.
    Returns True if a valid active company is present.

    Rules:
    - If no companies: False (caller should redirect to onboarding).
    - If active company missing/invalid: set the first available company.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False

    support = get_support_mode(request)
    if support.is_active and getattr(user, "is_staff", False):
        # In support mode, we don't require company membership.
        return True

    companies = list(user_companies_qs(user)[:2])
    if not companies:
        return False

    current_id = get_active_company_id(request)
    if current_id and any(str(c.id) == current_id for c in companies):
        return True

    # Prefer the first company (deterministic ordering by name then created)
    first = user_companies_qs(user).order_by("name", "created_at").first()
    if not first:
        return False
    set_active_company_id(request, str(first.id))
    return True


def get_active_company(request: HttpRequest) -> Company | None:
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None

    support = get_support_mode(request)
    cid = get_active_company_id(request)
    if support.is_active and getattr(user, "is_staff", False):
        # In support mode, the chosen company is forced to the support target.
        target_id = support.company_id or cid
        if not target_id:
            return None
        try:
            return Company.objects.filter(deleted_at__isnull=True).get(id=target_id)
        except Exception:
            return None

    if not cid:
        return None
    try:
        return user_companies_qs(user).get(id=cid)
    except Exception:
        return None


class _SupportEmployee:
    """Lightweight EmployeeProfile-like object for staff support mode."""
    def __init__(self, *, company: Company, user):
        self.company = company
        self.user = user
        self.role = "owner"
        self.username_public = getattr(user, "username", "") or getattr(user, "email", "")
        self.display_name = (getattr(user, "get_full_name", lambda: "")() or "").strip()
        self.force_2fa = True
        self.can_view_company_financials = True
        self.can_approve_time = False


def get_active_employee_profile(request: HttpRequest):
    company = get_active_company(request)
    user = getattr(request, "user", None)
    if not company or not user or not user.is_authenticated:
        return None

    support = get_support_mode(request)
    if support.is_active and getattr(user, "is_staff", False):
        return _SupportEmployee(company=company, user=user)

    return EmployeeProfile.objects.filter(company=company, user=user, deleted_at__isnull=True).first()


# -------------------------
# Invites
# -------------------------

import secrets
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from core.email_utils import EmailSpec, send_templated_email


INVITE_SESSION_KEY = "pending_invite_token"


def generate_invite_token() -> str:
    # ~43 chars url-safe; fits in 64
    return secrets.token_urlsafe(32)


def ensure_unique_username_public(company: Company, desired: str) -> str:
    base = (desired or "").strip()
    base = "".join(ch for ch in base if ch.isalnum() or ch in ("_", "-", "."))[:40]
    if not base:
        base = "user"
    candidate = base
    i = 2
    from .models import EmployeeProfile  # local import to avoid circulars

    while EmployeeProfile.objects.filter(company=company, username_public=candidate, deleted_at__isnull=True).exists():
        suffix = f"{i}"
        candidate = (base[: (40 - len(suffix))] + suffix)[:40]
        i += 1
    return candidate


def send_company_invite_email(request: HttpRequest, invite) -> None:
    """Send a templated invite email (HTML + text)."""
    accept_url = request.build_absolute_uri(reverse("companies:invite_accept", args=[invite.token]))

    context = {
        "site_name": getattr(settings, "SITE_NAME", "EZ360PM"),
        "company_name": invite.company.name,
        "role": invite.get_role_display(),
        "username_public": invite.username_public,
        "accept_url": accept_url,
        "support_email": getattr(settings, "SUPPORT_EMAIL", ""),
    }

    spec = EmailSpec(
        subject=f"You've been invited to {context['site_name']} ({invite.company.name})",
        to=[invite.email],
        context=context,
        template_html="emails/company_invite.html",
        template_txt="emails/company_invite.txt",
        reply_to=[context["support_email"]] if context["support_email"] else None,
    )

    # In dev we don't want failures to break flows; in prod, surface email issues.
    fail_silently = getattr(settings, "DEBUG", False)
    send_templated_email(spec, fail_silently=fail_silently)


def remember_pending_invite(request: HttpRequest, token: str) -> None:
    request.session[INVITE_SESSION_KEY] = token


def pop_pending_invite(request: HttpRequest) -> str:
    return str(request.session.pop(INVITE_SESSION_KEY, "") or "")


def build_login_redirect_with_next(request: HttpRequest, next_url: str) -> str:
    # accounts:login supports ?next=
    return f"{reverse('accounts:login')}?next={next_url}"
