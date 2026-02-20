from django.urls import path

from . import views
from . import views_support


app_name = "core"


urlpatterns = [
    path("", views.home, name="home"),
    path("pricing/", views.pricing, name="pricing"),
    path("app/", views.app_dashboard, name="app_dashboard"),
    path("app/dashboard/customize/", views.dashboard_customize, name="dashboard_customize"),
    path("app/dashboard/api/revenue-trend/", views.dashboard_revenue_trend_api, name="dashboard_revenue_trend_api"),
    path("app/dashboard/api/ar-aging/", views.dashboard_ar_aging_api, name="dashboard_ar_aging_api"),
    path("getting-started/", views.getting_started, name="getting_started"),
    path("health/", views.health, name="health"),
    path("search/", views.global_search, name="search"),

    path("support/mode/", views_support.support_mode_status, name="support_mode_status"),
    path("support/mode/enter/", views_support.support_mode_enter, name="support_mode_enter"),
    path("support/mode/exit/", views_support.support_mode_exit, name="support_mode_exit"),
]
