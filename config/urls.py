# config/urls.py
from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # Auth
    path("accounts/", include("accounts.urls")),

    # Main app areas
    path("", include("dashboard.urls")),                # dashboard + landing
    path("app/", include("core.urls")),                 # clients, projects, invoices, etc.
    path("billing/", include("billing.urls")),          # subscriptions, portal
    path("timetracking/", include("timetracking.urls")),
    path("projects/", include("projects.urls")),
    path("invoices/", include("invoices.urls")),
    path("company/", include("company.urls")),
    path("payments/", include("payments.urls")),
    path("expenses/", include("expenses.urls")),
    path("clients/", include("clients.urls")),

    # Optional sub-apps
    path("help/", include(("helpcenter.urls", "help"), namespace="help")),
    path("onboarding/", include(("onboarding.urls", "onboarding"), namespace="onboarding")),
]

# Media (dev only)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Optional: Debug Toolbar
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar # type: ignore
        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
