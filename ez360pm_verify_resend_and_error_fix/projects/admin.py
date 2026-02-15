from django.contrib import admin

from core.admin_mixins import IncludeSoftDeletedAdminMixin

from .models import Project, ProjectService, ProjectFile


class ProjectServiceInline(admin.TabularInline):
    model = ProjectService
    extra = 0


@admin.register(Project)
class ProjectAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    list_display = ("project_number", "name", "company", "client", "assigned_to", "billing_type", "due_date", "deleted_at")
    list_filter = ("company", "billing_type", "is_active")
    search_fields = ("project_number", "name", "client__company_name", "client__last_name", "client__first_name")
    inlines = [ProjectServiceInline]


@admin.register(ProjectService)
class ProjectServiceAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "project", "deleted_at")
    search_fields = ("name", "project__name", "project__project_number")


@admin.register(ProjectFile)
class ProjectFileAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    list_display = ("project", "title", "company", "uploaded_by", "created_at", "deleted_at")
    list_filter = ("company", "deleted_at")
    search_fields = ("title", "notes", "file")
    raw_id_fields = ("project", "company", "uploaded_by", "updated_by_user")
