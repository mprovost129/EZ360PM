# helpcenter/admin.py
from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import path

from .models import HelpCenterScreenshot
from .required_screenshots import REQUIRED_HELP_SCREENSHOT_KEYS


@admin.register(HelpCenterScreenshot)
class HelpCenterScreenshotAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "updated_at")
    search_fields = ("key", "title")
    ordering = ("key",)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "required-keys/",
                self.admin_site.admin_view(self.required_keys_view),
                name="helpcenter_helpcenterscreenshot_required_keys",
            ),
        ]
        return custom + urls

    def required_keys_view(self, request: HttpRequest) -> HttpResponse:
        existing = set(HelpCenterScreenshot.objects.values_list("key", flat=True))
        required = list(REQUIRED_HELP_SCREENSHOT_KEYS)
        missing = [k for k in required if k not in existing]
        extra = sorted(list(existing - set(required)))

        context = {
            **self.admin_site.each_context(request),
            "title": "Help Center screenshots — required keys",
            "required": required,
            "missing": missing,
            "extra": extra,
            "existing_count": len(existing),
            "required_count": len(required),
            "missing_count": len(missing),
        }
        return TemplateResponse(request, "admin/helpcenter/helpcenterscreenshot/required_keys.html", context)
