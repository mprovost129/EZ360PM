# accounts/admin.py
from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from django.contrib.auth.models import Permission  # ✅ needed for PermissionAdmin

from .models import User, UserProfile


class UserProfileInline(admin.StackedInline):
    """Inline profile editor for each User."""
    model = UserProfile
    can_delete = False
    fk_name = "user"
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for the User model using email as the username."""

    model = User
    ordering = ("-date_joined",)
    list_display = ("email", "name", "is_verified", "is_staff", "is_superuser", "date_joined")
    list_filter = ("is_staff", "is_superuser", "is_active", "is_verified", "groups")
    search_fields = ("email", "name")
    inlines = [UserProfileInline]

    readonly_fields = ("date_joined", "last_login", "accepted_tos_at", "accepted_privacy_at")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("name",)}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_verified",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            _("Important dates"),
            {
                "fields": (
                    "last_login",
                    "date_joined",
                    "accepted_tos_at",
                    "accepted_privacy_at",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "name", "password1", "password2", "is_verified"),
            },
        ),
    )

    # Uses autocomplete for groups and permissions; requires a registered PermissionAdmin with search_fields.
    autocomplete_fields = ("groups", "user_permissions")


# ---------------------------------------------------------------------
# Enable autocomplete for user_permissions (fixes admin.E039)
# ---------------------------------------------------------------------
@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    search_fields = (
        "name",
        "codename",
        "content_type__app_label",
        "content_type__model",
    )
    list_display = ("name", "codename", "content_type")
    list_filter = ("content_type",)
