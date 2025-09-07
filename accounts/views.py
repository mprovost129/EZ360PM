# accounts/views.py
from __future__ import annotations

from typing import Iterable, Optional

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.core.mail import EmailMessage
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render, resolve_url
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes, force_str
from django.utils.http import (
    url_has_allowed_host_and_scheme,
    urlsafe_base64_decode,
    urlsafe_base64_encode,
)
from django.views.decorators.http import require_POST

from .utils import get_user_profile
from company.models import Company, CompanyMember
from company.utils import get_active_company, get_user_companies, set_active_company
from core.utils import get_user_membership
from .forms import LoginForm, RegisterForm, UserProfileForm
from .tokens import email_verification_token

User = get_user_model()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _safe_next(request: HttpRequest, default_name: str = "dashboard:home") -> str:
    """
    Return a safe redirect target, preferring ?next= when it points to our host.
    Falls back to `default_name` resolved URL.
    """
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return resolve_url(default_name)


def _send_verification_email(request: HttpRequest, user: User) -> None:  # type: ignore[override]
    app_name = getattr(settings, "APP_NAME", "EZ360PM")
    site_url = getattr(settings, "SITE_URL", "")
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    verify_url = request.build_absolute_uri(
        reverse("accounts:verify_email", kwargs={"uidb64": uid, "token": token})
    )
    body = render_to_string(
        "accounts/email/verify_email.txt",
        {"user": user, "verify_url": verify_url, "app_name": app_name, "site_url": site_url},
    )
    EmailMessage(
        subject=f"Verify your email • {app_name}",
        body=body,
        to=[user.email],
    ).send(fail_silently=False)


def _compose_name_from_form(first: Optional[str], last: Optional[str], fallback: str) -> str:
    """
    Combine first/last into a single display name when present.
    Falls back to given fallback (e.g., existing user.name or email).
    """
    f = (first or "").strip()
    l = (last or "").strip()
    if f and l:
        return f"{f} {l}"
    if f:
        return f
    if l:
        return l
    return fallback


# ----------------------------------------------------------------------
# Auth: Login / Logout / Register
# ----------------------------------------------------------------------
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect(_safe_next(request))

    next_url = _safe_next(request)

    if request.method == "POST":
        form = LoginForm(request.POST, request=request)  # <-- pass request
        if form.is_valid():
            user = form.cleaned_data.get("user")
            if user is not None:
                login(request, user)  # backend is set by authenticate()
                messages.success(request, "Welcome back!")
                return redirect(next_url)
            form.add_error(None, "Authentication failed. Please try again.")
    else:
        form = LoginForm(request=request)

    return render(request, "accounts/login.html", {"form": form, "next": next_url})


def logout_view(request: HttpRequest) -> HttpResponse:
    next_url = _safe_next(request, default_name="accounts:login")
    logout(request)  # clears session (incl. any active_company)
    messages.info(request, "You’ve been logged out.")
    return redirect(next_url)


def register_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user: User = form.save()  # type: ignore[assignment]

            # IMPORTANT: specify which auth backend to use
            login(request, user, backend="accounts.backends.EmailBackend")

            # Starter company + membership
            display = (getattr(user, "name", "") or user.email).strip()
            company = Company.objects.create(owner=user, name=f"{display} — Company")
            CompanyMember.objects.get_or_create(
                company=company, user=user, defaults={"role": CompanyMember.OWNER}
            )
            set_active_company(request, company)

            # Ensure related profile exists
            get_user_profile(user)

            # Send verification and nudge user to verify
            _send_verification_email(request, user)
            messages.success(request, "Welcome! Please verify your email to unlock everything.")
            return redirect("accounts:verify_needed")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


# ----------------------------------------------------------------------
# Password change / reset (Django CBVs)
# ----------------------------------------------------------------------
class CaseInsensitivePasswordResetForm(PasswordResetForm):
    """
    Allow password reset by email ignoring case for custom User.
    Only returns active users with usable passwords, as Django expects.
    """
    def get_users(self, email: Optional[str]) -> Iterable[User]:  # type: ignore[override]
        if not email:
            return []
        return (
            User._default_manager.filter(email__iexact=email.strip(), is_active=True)
            .filter(**{f"{User.USERNAME_FIELD}__isnull": False})
            .iterator()
        )


password_change = login_required(
    auth_views.PasswordChangeView.as_view(
        template_name="accounts/password_change_form.html",
        success_url=reverse_lazy("accounts:password_change_done"),
        form_class=PasswordChangeForm,
    )
)

password_change_done = login_required(
    auth_views.PasswordChangeDoneView.as_view(
        template_name="accounts/password_change_done.html",
    )
)

password_reset = auth_views.PasswordResetView.as_view(
    template_name="accounts/password_reset_form.html",
    email_template_name="accounts/email/password_reset_email.txt",
    subject_template_name="accounts/email/password_reset_subject.txt",
    success_url=reverse_lazy("accounts:password_reset_done"),
    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
    form_class=CaseInsensitivePasswordResetForm,
)

password_reset_done = auth_views.PasswordResetDoneView.as_view(
    template_name="accounts/password_reset_done.html",
)

password_reset_confirm = auth_views.PasswordResetConfirmView.as_view(
    template_name="accounts/password_reset_confirm.html",
    success_url=reverse_lazy("accounts:password_reset_complete"),
    form_class=SetPasswordForm,
)

password_reset_complete = auth_views.PasswordResetCompleteView.as_view(
    template_name="accounts/password_reset_complete.html",
)


# ----------------------------------------------------------------------
# Email verification
# ----------------------------------------------------------------------
def verify_needed(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated and getattr(request.user, "is_verified", False):
        return redirect("dashboard:home")
    return render(request, "accounts/verify_needed.html")


@require_POST
def verify_resend(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated and not getattr(request.user, "is_verified", False):
        _send_verification_email(request, request.user)  # type: ignore[arg-type]
        messages.success(request, "Verification email sent.")
    return redirect("accounts:verify_needed")


def verify_email(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except Exception:
        user = None

    if user and email_verification_token.check_token(user, token):
        if not getattr(user, "is_verified", False):
            setattr(user, "is_verified", True)
            user.save(update_fields=["is_verified"])
        messages.success(request, "Email verified! You’re all set.")
        # Route to your primary app landing
        return redirect("dashboard:home")

    messages.error(request, "That verification link is invalid or expired.")
    return redirect("accounts:verify_needed")


# ----------------------------------------------------------------------
# User Profile
# ----------------------------------------------------------------------
@login_required
def my_profile(request: HttpRequest) -> HttpResponse:
    user = request.user
    company = get_active_company(request)
    profile = get_user_profile(user)

    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            profile = form.save()

            # Accept either (first_name/last_name) or a single "name" field from the form.
            first = (form.cleaned_data.get("first_name") or "").strip()
            last = (form.cleaned_data.get("last_name") or "").strip()
            explicit_name = (form.cleaned_data.get("name") or "").strip()
            new_name = explicit_name or _compose_name_from_form(first, last, getattr(user, "name", "") or user.email) # type: ignore

            if hasattr(user, "name") and new_name and new_name != (user.name or ""): # type: ignore
                user.name = new_name # type: ignore
                user.save(update_fields=["name"]) # type: ignore

            messages.success(request, "Profile updated.")
            return redirect("accounts:my_profile")
    else:
        # Prefill initial name fields if your form supports them
        # (safe to include both: form may ignore unused initial keys)
        initial = {
            "name": getattr(request.user, "name", "") or "",
            "first_name": (getattr(request.user, "name", "") or "").split(" ", 1)[0] if getattr(request.user, "name", "") else "",
            "last_name": (getattr(request.user, "name", "") or "").split(" ", 1)[1] if " " in (getattr(request.user, "name", "") or "") else "",
        }
        form = UserProfileForm(instance=profile, initial=initial)

    membership = get_user_membership(user, company) if company else None
    companies = get_user_companies(user)

    return render(
        request,
        "accounts/profile.html",
        {
            "form": form,
            "profile": profile,
            "company": company,
            "membership": membership,
            "companies": companies,
        },
    )


@login_required
def my_profile_edit(request: HttpRequest) -> HttpResponse:
    """
    If you keep a separate edit page, this mirrors my_profile's POST handling.
    """
    company = get_active_company(request)
    profile = get_user_profile(request.user)

    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()

            first = (form.cleaned_data.get("first_name") or "").strip()
            last = (form.cleaned_data.get("last_name") or "").strip()
            explicit_name = (form.cleaned_data.get("name") or "").strip()
            new_name = explicit_name or _compose_name_from_form(first, last, getattr(request.user, "name", "") or request.user.email) # type: ignore

            if hasattr(request.user, "name") and new_name and new_name != (getattr(request.user, "name", "") or ""):
                request.user.name = new_name # type: ignore
                request.user.save(update_fields=["name"]) # type: ignore

            messages.success(request, "Profile updated.")
            return redirect("accounts:my_profile")
    else:
        initial = {
            "name": getattr(request.user, "name", "") or "",
            "first_name": (getattr(request.user, "name", "") or "").split(" ", 1)[0] if getattr(request.user, "name", "") else "",
            "last_name": (getattr(request.user, "name", "") or "").split(" ", 1)[1] if " " in (getattr(request.user, "name", "") or "") else "",
        }
        form = UserProfileForm(instance=profile, initial=initial)

    return render(
        request,
        "accounts/profile_form.html",
        {"form": form, "company": company, "profile": profile},
    )
