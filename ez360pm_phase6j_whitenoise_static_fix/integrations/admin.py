from django.contrib import admin

from .models import DropboxConnection


@admin.register(DropboxConnection)
class DropboxConnectionAdmin(admin.ModelAdmin):
    list_display = ("company", "is_active", "account_id", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("company__name", "account_id")
    readonly_fields = ("created_at", "updated_at")


from .models import IntegrationConfig


@admin.register(IntegrationConfig)
class IntegrationConfigAdmin(admin.ModelAdmin):
    list_display = ("company", "use_dropbox_for_project_files", "updated_at")
    list_select_related = ("company",)
    search_fields = ("company__name",)
