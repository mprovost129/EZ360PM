from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import PasswordResetRequestForm, SetNewPasswordForm

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),

    # Email verification (Pack P)
    path("verify-email/<str:token>/", views.verify_email, name="verify_email"),
    path("verify-email/resend/", views.resend_verification, name="verify_email_resend"),

    # Gate page (Hardening Phase)
    path("verify-required/", views.verify_required, name="verify_required"),

    # Password reset (Pack P) - Django built-ins with our templates
    path(
        "password-reset/",
        views.RecaptchaPasswordResetView.as_view(
            form_class=PasswordResetRequestForm,
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.txt",
            html_email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
            success_url="/accounts/password-reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            form_class=SetNewPasswordForm,
            template_name="registration/password_reset_confirm.html",
            success_url="/accounts/reset/done/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),

    # 2FA (Pack N)
    path("2fa/setup/", views.two_factor_setup, name="two_factor_setup"),
    path("2fa/verify/", views.two_factor_verify, name="two_factor_verify"),
    path("2fa/disable/", views.two_factor_disable, name="two_factor_disable"),
]
