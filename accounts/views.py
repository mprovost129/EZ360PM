# accounts/views.py
from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.core.mail import EmailMessage
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

from core.models import Company, CompanyMember
from core.utils import get_user_profile, set_active_company
from .forms import LoginForm, RegisterForm
from .tokens import email_verification_token

User = get_user_model()


# ---------- Helpers ----------
def _safe_next(request, default_name: str = "dashboard:home") -> str:
    """Return a safe redirect target (prefers ?next= on our host/HTTPS)."""
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return resolve_url(default_name)


def _send_verification_email(request, user: User) -> None: # type: ignore
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    verify_url = request.build_absolute_uri(
        reverse("accounts:verify_email", kwargs={"uidb64": uid, "token": token})
    )
    body = render_to_string(
        "accounts/email/verify_email.txt",
        {
            "user": user,
            "verify_url": verify_url,
            "app_name": getattr(settings, "APP_NAME", "UltraPM"),
            "site_url": getattr(settings, "SITE_URL", ""),
        },
    )
    EmailMessage(
        subject=f"Verify your email • {getattr(settings, 'APP_NAME', 'UltraPM')}",
        body=body,
        to=[user.email],
    ).send(fail_silently=False)


# ---------- Auth: Login / Logout / Register ----------
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))

    next_url = _safe_next(request)

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data.get("user")
            if user is not None:
                login(request, user)  # rotates session
                messages.success(request, "Welcome back!")
                return redirect(next_url)
            form.add_error(None, "Authentication failed. Please try again.")
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form, "next": next_url})


def logout_view(request):
    next_url = _safe_next(request, default_name="accounts:login")
    logout(request)  # clears session (incl. active_company)
    messages.info(request, "You’ve been logged out.")
    return redirect(next_url)


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user: User = form.save() # type: ignore
            login(request, user)

            # Starter company + membership (optional—keeps onboarding simple)
            display = (getattr(user, "name", "") or user.email).strip()
            company = Company.objects.create(owner=user, name=f"{display} — Company")
            CompanyMember.objects.get_or_create(
                company=company, user=user, defaults={"role": CompanyMember.OWNER}
            )
            set_active_company(request, company)

            # Ensure profile exists
            get_user_profile(user)

            # Send verification and nudge user to verify first
            _send_verification_email(request, user)
            messages.success(request, "Welcome! Please verify your email to unlock everything.")
            return redirect("accounts:verify_needed")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


# ---------- Password change / reset (Django CBVs) ----------
class CaseInsensitivePasswordResetForm(PasswordResetForm):
    """Allow reset by email ignoring case for custom User."""
    def get_users(self, email):  # type: ignore[override]
        if not email:
            return []
        return User._default_manager.filter(email__iexact=email, is_active=True)


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
    email_template_name="accounts/emails/password_reset_email.txt",
    subject_template_name="accounts/emails/password_reset_subject.txt",
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


# ---------- Email verification ----------
def verify_needed(request):
    if request.user.is_authenticated and getattr(request.user, "is_verified", False):
        return redirect("dashboard:home")
    return render(request, "accounts/verify_needed.html")


@require_POST
def verify_resend(request):
    if request.user.is_authenticated and not getattr(request.user, "is_verified", False):
        _send_verification_email(request, request.user)
        messages.success(request, "Verification email sent.")
    return redirect("accounts:verify_needed")


def verify_email(request, uidb64: str, token: str):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except Exception:
        user = None

    if user and email_verification_token.check_token(user, token):
        if not getattr(user, "is_verified", False):
            user.is_verified = True  # type: ignore # field lives on your custom User
            user.save(update_fields=["is_verified"])
        messages.success(request, "Email verified! You’re all set.")
        # Head into your onboarding wizard (adjust if you use a different route)
        return redirect("dashboard:welcome")
    messages.error(request, "That verification link is invalid or expired.")
    return redirect("accounts:verify_needed")
