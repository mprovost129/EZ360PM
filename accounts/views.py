from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.cache import cache
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from datetime import timedelta

from core.recaptcha import passes_policy, recaptcha_is_enabled, verify_recaptcha
from core.throttle import hit

from companies.services import pop_pending_invite, user_companies_qs

from .email_verification import parse_verify_token, send_verify_email
from .forms import (
    LoginForm,
    RegisterForm,
    TwoFactorSetupVerifyForm,
    TwoFactorVerifyForm,
)
from .models import TwoFactorSettings, LoginEvent
from .security import log_login_success
from .two_factor import build_otpauth_url, generate_base32_secret, verify_totp


User = get_user_model()


def _post_login_redirect(request, user):
    pending = pop_pending_invite(request)
    if pending:
        return redirect("companies:invite_accept", token=pending)

    if not user_companies_qs(user).exists():
        return redirect("companies:onboarding")
    return redirect("core:app_dashboard")


def _client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "unknown"


def _require_recaptcha(request, *, action: str) -> bool:
    if not recaptcha_is_enabled():
        return True
    token = request.POST.get("recaptcha_token", "")
    res = verify_recaptcha(token, remoteip=_client_ip(request))
    return passes_policy(res, expected_action=action)


def _throttle_or_block(request, *, prefix: str, limit: int, window_seconds: int) -> bool:
    result = hit(prefix, _client_ip(request), limit=limit, window_seconds=window_seconds)
    return result.allowed


def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:app_dashboard")

    form = LoginForm(request, data=request.POST or None)

    if request.method == "POST":
        # IP throttle (coarse)
        if not _throttle_or_block(request, prefix="login", limit=20, window_seconds=60 * 10):
            messages.error(request, "Too many login attempts. Please wait a few minutes and try again.")
            return render(request, "accounts/login.html", {"form": form})

        # Account-based progressive lockout (Hardening Phase)
        ident = (request.POST.get("username") or request.POST.get("email") or "").strip().lower()
        if ident:
            from .lockouts import get_status, record_failure, clear as clear_lockout

            status = get_status(ident)
            if status.is_locked and status.locked_until:
                messages.error(
                    request,
                    "This account is temporarily locked due to failed login attempts. Please wait and try again, or contact your admin.",
                )
                return render(request, "accounts/login.html", {"form": form})

        # reCAPTCHA (Pack Q)
        if not _require_recaptcha(request, action="login"):
            messages.error(request, "reCAPTCHA verification failed. Please try again.")
            return render(request, "accounts/login.html", {"form": form})

        if form.is_valid():
            user = form.get_user()

            # Successful password auth: clear lockout and log event
            try:
                from .lockouts import clear as clear_lockout
                clear_lockout(user.email)
            except Exception:
                pass

            login(request, user)
            log_login_success(request, user, method=LoginEvent.METHOD_PASSWORD)
            messages.success(request, "Welcome back.")
            return _post_login_redirect(request, user)

        # Invalid credentials -> record failure
        ident = (request.POST.get("username") or request.POST.get("email") or "").strip().lower()
        if ident:
            try:
                from .lockouts import record_failure
                status = record_failure(ident)
                if status.is_locked:
                    messages.error(
                        request,
                        "Too many failed attempts. This account is now temporarily locked. Please wait or contact your admin.",
                    )
            except Exception:
                pass

        messages.error(request, "Invalid credentials. Please try again.")

    return render(request, "accounts/login.html", {"form": form})
def register_view(request):
    if request.user.is_authenticated:
        return redirect("core:app_dashboard")

    if request.method == "POST":
        # Throttle + reCAPTCHA (Pack Q)
        if not _throttle_or_block(request, prefix="register", limit=10, window_seconds=60 * 10):
            messages.error(request, "Too many sign-up attempts. Please wait a few minutes and try again.")
            form = RegisterForm(request.POST)
            return render(request, "accounts/register.html", {"form": form})

        if not _require_recaptcha(request, action="register"):
            messages.error(request, "reCAPTCHA verification failed. Please try again.")
            form = RegisterForm(request.POST)
            return render(request, "accounts/register.html", {"form": form})

        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = (user.email or "").lower()
            user.save()

            # Send verification email (does not block login by default).
            try:
                send_verify_email(request, user)
                messages.info(request, "We sent you a verification email. Please verify to secure your account.")
            except Exception:
                messages.warning(request, "Account created, but we couldn't send a verification email yet.")

            login(request, user)

            pending = pop_pending_invite(request)
            if pending:
                return redirect("companies:invite_accept", token=pending)

            messages.success(request, "Account created. Please create your company.")
            return redirect("companies:onboarding")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("core:home")


@login_required
@login_required
def profile_view(request):
    login_events = LoginEvent.objects.filter(user=request.user).order_by('-created_at')[:20]
    return render(request, "accounts/profile.html", {"login_events": login_events})


@login_required
def resend_verification(request):
    if getattr(request.user, "email_verified", False):
        messages.info(request, "Your email is already verified.")
        return redirect("accounts:profile")

    try:
        send_verify_email(request, request.user)
        messages.success(request, "Verification email sent. Check your inbox.")
    except Exception:
        messages.error(request, "We couldn't send the verification email yet. Try again later.")
    return redirect("accounts:profile")


def verify_email(request, token: str):
    try:
        data = parse_verify_token(token)
    except signing.BadSignature:
        raise Http404("Invalid token")
    except signing.SignatureExpired:
        messages.error(request, "That verification link has expired. Please request a new one.")
        return redirect("accounts:login")

    try:
        user = User.objects.get(pk=data.user_id)
    except User.DoesNotExist:
        raise Http404("User not found")

    if user.email.lower() != data.email.lower():
        raise Http404("Token mismatch")

    if getattr(user, "email_verified", False):
        messages.info(request, "Your email is already verified.")
    else:
        user.mark_email_verified()
        messages.success(request, "Email verified. Thanks!")

    if request.user.is_authenticated:
        return redirect("accounts:profile")
    return redirect("accounts:login")


@login_required
def two_factor_setup(request):
    tf, _ = TwoFactorSettings.objects.get_or_create(user=request.user)
    if tf.is_enabled:
        messages.info(request, "Two-factor authentication is already enabled.")
        return redirect("accounts:profile")

    if not tf.secret:
        tf.secret = generate_base32_secret()
        tf.save(update_fields=["secret"])

    otpauth_url = build_otpauth_url(request.user.email, tf.secret)

    if request.method == "POST":
        form = TwoFactorSetupVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            if verify_totp(tf.secret, code):
                tf.is_enabled = True
                tf.verified_at = timezone.now()
                tf.last_used_at = timezone.now()
                tf.save(update_fields=["is_enabled", "verified_at", "last_used_at"])
                messages.success(request, "Two-factor authentication enabled.")
                return redirect("accounts:profile")
        messages.error(request, "Invalid code. Please try again.")
    else:
        form = TwoFactorSetupVerifyForm()

    return render(
        request,
        "accounts/two_factor_setup.html",
        {"form": form, "secret": tf.secret, "otpauth_url": otpauth_url},
    )


def two_factor_verify(request):
    if request.user.is_authenticated:
        return redirect("core:app_dashboard")

    user_id = request.session.get("two_factor_pending_user_id")
    if not user_id:
        return redirect("accounts:login")

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        request.session.pop("two_factor_pending_user_id", None)
        return redirect("accounts:login")

    tf = getattr(user, "two_factor", None)
    if not tf or not tf.is_enabled or not tf.secret:
        request.session.pop("two_factor_pending_user_id", None)
        return redirect("accounts:login")

    if request.method == "POST":
        form = TwoFactorVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            if verify_totp(tf.secret, code):
                login(request, user)
                log_login_success(request, user, method="2fa")
                tf.last_used_at = timezone.now()
                tf.save(update_fields=["last_used_at"])
                request.session.pop("two_factor_pending_user_id", None)
                request.session.pop("two_factor_pending_at", None)
                messages.success(request, "Two-factor verification successful.")
                return _post_login_redirect(request, user)

        messages.error(request, "Invalid code. Please try again.")
    else:
        form = TwoFactorVerifyForm()

    return render(request, "accounts/two_factor_verify.html", {"form": form, "email": user.email})
def two_factor_disable(request):
    tf, _ = TwoFactorSettings.objects.get_or_create(user=request.user)
    if not tf.is_enabled:
        messages.info(request, "Two-factor authentication is already disabled.")
        return redirect("accounts:profile")

    if request.method == "POST":
        tf.is_enabled = False
        tf.secret = ""
        tf.verified_at = None
        tf.last_used_at = None
        tf.save(update_fields=["is_enabled", "secret", "verified_at", "last_used_at"])
        messages.success(request, "Two-factor authentication disabled.")
        return redirect("accounts:profile")

    return render(request, "accounts/two_factor_disable.html")


class RecaptchaPasswordResetView(auth_views.PasswordResetView):
    """
    Password reset with throttling + reCAPTCHA v3 (Pack Q).

    Note: If RECAPTCHA is disabled, this behaves like the normal Django view.
    """

    def post(self, request, *args, **kwargs):
        if not _throttle_or_block(request, prefix="password_reset", limit=8, window_seconds=60 * 15):
            messages.error(request, "Too many reset attempts. Please wait and try again.")
            return self.get(request, *args, **kwargs)

        if not _require_recaptcha(request, action="password_reset"):
            messages.error(request, "reCAPTCHA verification failed. Please try again.")
            return self.get(request, *args, **kwargs)

        return super().post(request, *args, **kwargs)


@login_required
def verify_required(request):
    # Gate page shown when user is authenticated but email is not verified.
    if getattr(request.user, "email_verified", False):
        return redirect("core:app_dashboard")
    return render(request, "accounts/verify_required.html", {})
