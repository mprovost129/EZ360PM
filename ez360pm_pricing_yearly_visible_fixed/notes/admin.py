from django.contrib import admin

from notes.models import UserNote


@admin.register(UserNote)
class UserNoteAdmin(admin.ModelAdmin):
    list_display = ("created_at", "company", "created_by", "subject", "contact_name")
    list_filter = ("company", "created_at")
    search_fields = ("subject", "body", "contact_name", "contact_email", "contact_phone")
    readonly_fields = ("created_at", "updated_at")
