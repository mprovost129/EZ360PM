from django.contrib import admin
from django.urls import include, path
from ezadmin.sites import ops_admin_site, customers_admin_site
from django.conf import settings
from django.conf.urls.static import static

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from ops import views as ops_views
from core import views_health


urlpatterns = [
    path("healthz/", ops_views.healthz, name="healthz"),
    path("version/", ops_views.version, name="version"),

    # Health checks (safe for monitors)
    path("health/", views_health.health, name="health"),
    path("health/details/", views_health.health_details, name="health_details"),

    # Public + app pages
    path("", include("core.urls")),
    path("", include("helpcenter.urls")),
    path("accounts/", include("accounts.urls")),
    path("companies/", include("companies.urls")),
    path("", include("integrations.urls")),
    path("", include("billing.urls")),
    path("", include("crm.urls")),
    path("", include("projects.urls")),
    path("", include("catalog.urls")),
    path("", include("timetracking.urls")),
    path("", include("documents.urls")),
    path("", include("payments.urls")),
    path("", include("expenses.urls")),
    path("", include("payables.urls")),
    path("", include("notes.urls")),
    path("", include("audit.urls")),

    path("", include("accounting.urls")),

    path("ops/", include("ops.urls")),
    # Admin portals
    path("ops-admin/", ops_admin_site.urls),
    path("customers-admin/", customers_admin_site.urls),

    # Legacy Django admin (keep for now; we can remove once Ops/Customers admin is complete)
    path("admin/", admin.site.urls),

    # API auth (JWT)
    path("api/v1/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # Sync API
    path("api/v1/sync/", include("sync.urls")),

    # S3 direct upload presign endpoint
    path("", include("projects.storage.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = 'core.error_views.error_404'
handler500 = 'core.error_views.error_500'
