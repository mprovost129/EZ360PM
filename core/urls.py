# core/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    # -----------------------------------------------------------------
    # Reports
    # -----------------------------------------------------------------
    path("reports/", views.reports, name="reports"),
    path("reports/pnl/", views.report_pnl, name="report_pnl"),
    path("reports/pnl/csv/", views.report_pnl_csv, name="report_pnl_csv"),
    # Legacy back-compat: dotted suffix (can be removed later)
    path("reports/pnl.csv", views.report_pnl_csv, name="report_pnl_csv_legacy"),

    # -----------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------
    path("search/", views.search, name="search"),

    # -----------------------------------------------------------------
    # Notifications
    # -----------------------------------------------------------------
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/list/", views.notifications_list, name="notifications_list"),
    path("notifications/read/<int:pk>/", views.notification_read, name="notification_read"),
    path("notifications/read-all/", views.notifications_read_all, name="notifications_read_all"),
    path("notifications/mark-all-read/", views.notifications_mark_all_read, name="notifications_mark_all_read"),
]
