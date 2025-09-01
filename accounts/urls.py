# accounts/urls.py
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Auth
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),

    # Password management
    path("password/change/", views.password_change, name="password_change"),
    path("password/change/done/", views.password_change_done, name="password_change_done"),
    path("password/reset/", views.password_reset, name="password_reset"),
    path("password/reset/done/", views.password_reset_done, name="password_reset_done"),
    path(
        "password/reset/confirm/<uidb64>/<token>/",
        views.password_reset_confirm,
        name="password_reset_confirm",
    ),
    path("password/reset/complete/", views.password_reset_complete, name="password_reset_complete"),

    # Email verification
    path("verify-needed/", views.verify_needed, name="verify_needed"),
    path("verify-resend/", views.verify_resend, name="verify_resend"),
    path("verify/<uidb64>/<token>/", views.verify_email, name="verify_email"),
]
