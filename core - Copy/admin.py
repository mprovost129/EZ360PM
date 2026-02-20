from django.contrib import admin

from .models import DashboardLayout


@admin.register(DashboardLayout)
class DashboardLayoutAdmin(admin.ModelAdmin):
    list_display = ("company", "role", "updated_at", "updated_by_user")
    list_filter = ("role",)
    search_fields = ("company__name",)
