from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, TwoFactorSettings, LoginEvent, AccountLockout


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin for custom User (email-first auth).

    Note: The underlying `username` field remains for AbstractUser compatibility,
    but EZ360PM does not use it as a public handle.
    """

    ordering = ("email",)
    list_display = ("email", "email_verified", "is_active", "is_staff", "is_superuser", "date_joined")
    search_fields = ("email", "first_name", "last_name")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name")}),
        ("Email Verification", {"fields": ("email_verified", "email_verified_at")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "is_active", "is_staff"),
            },
        ),
    )

# Register your models here.


@admin.register(TwoFactorSettings)
class TwoFactorSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "is_enabled", "verified_at", "last_used_at", "updated_at")
    search_fields = ("user__email",)
    list_filter = ("is_enabled",)


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "method", "ip_address")
    search_fields = ("user__email", "ip_address", "user_agent")
    list_filter = ("method", "created_at")
    ordering = ("-created_at",)


@admin.register(AccountLockout)
class AccountLockoutAdmin(admin.ModelAdmin):
    list_display = ("identifier", "failed_count", "locked_until", "last_failed_at", "updated_at")
    search_fields = ("identifier",)
    list_filter = ("locked_until",)
