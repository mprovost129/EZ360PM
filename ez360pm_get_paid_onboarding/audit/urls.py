from __future__ import annotations

from django.urls import path

from . import views

app_name = "audit"

urlpatterns = [
    path("audit/", views.audit_event_list, name="event_list"),
    path("audit/export.csv", views.audit_event_export_csv, name="event_export_csv"),
    path("audit/<uuid:pk>/", views.audit_event_detail, name="event_detail"),
]
