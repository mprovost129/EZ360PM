# accounts/views.py
from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.shortcuts import render, redirect, resolve_url
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from typing import Optional
from core.models import Company, CompanyMember
from core.utils import set_active_company, get_user_profile
from .forms import RegisterForm, LoginForm

User = get_user_model()


# ---------- Helpers ----------
def _safe_next(request, default_name: str = "dashboard:home") -> str:
    """
    Returns a safe URL to redirect to after login/logout.
    Prefers ?next= from POST then GET, but only if it's on our host.
    Falls back to a named URL.
    """
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return resolve_url(default_name)


# ---------- Auth: Login / Logout / Register ----------
def login_view(request):
    # If already signed in, go where they were headed.
    if request.user.is_authenticated:
        return redirect(_safe_next(request))

    next_url = _safe_next(request)

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data.get("user")
            if user is not None:
                login(request, user)  # rotates session key
                messages.success(request, "Welcome back!")
                return redirect(next_url)
            form.add_error(None, "Authentication failed. Please try again.")
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form, "next": next_url})


def logout_view(request):
    next_url = _safe_next(request, default_name="accounts:login")
    logout(request)  # clears session (incl. any active_company)
    messages.info(request, "You’ve been logged out.")
    return redirect(next_url)


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)

            # Create a starter company and membership
            default_name = (getattr(user, "name", "") or user.email).strip()
            company = Company.objects.create(owner=user, name=f"{default_name} — Company")
            CompanyMember.objects.get_or_create(
                company=company, user=user, defaults={"role": CompanyMember.OWNER}
            )
            set_active_company(request, company)

            # Ensure a profile exists
            get_user_profile(user)

            messages.success(request, "Welcome aboard! Let’s set things up.")
            return redirect("onboarding:start")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


# ---------- Password Change / Reset (Django CBVs) ----------

# Optional: case-insensitive email lookup for password reset with custom user
class CaseInsensitivePasswordResetForm(PasswordResetForm):
    def get_users(self, email): # type: ignore
        if not email:
            return []
        return User._default_manager.filter(email__iexact=email, is_active=True)


# Password change (must be logged in)
password_change = login_required(auth_views.PasswordChangeView.as_view(
    template_name="accounts/password_change_form.html",
    success_url=reverse_lazy("accounts:password_change_done"),
    form_class=PasswordChangeForm,
))

password_change_done = login_required(auth_views.PasswordChangeDoneView.as_view(
    template_name="accounts/password_change_done.html",
))

# Password reset flow (email link)
password_reset = auth_views.PasswordResetView.as_view(
    template_name="accounts/password_reset_form.html",
    email_template_name="accounts/emails/password_reset_email.txt",
    subject_template_name="accounts/emails/password_reset_subject.txt",
    success_url=reverse_lazy("accounts:password_reset_done"),
    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
    form_class=CaseInsensitivePasswordResetForm,  # use PasswordResetForm if you prefer
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
