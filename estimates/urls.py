# estimates/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "estimates"

urlpatterns = [
    # Estimates (private)
    path("estimates/", views.estimates_list, name="estimates_list"),
    path("estimates/new/", views.estimate_create, name="estimate_create"),
    path("estimates/new/from/<int:pk>/", views.estimate_create_from, name="estimate_create_from"),
    path("estimates/<int:pk>/", views.estimate_detail, name="estimate_detail"),
    path("estimates/<int:pk>/edit/", views.estimate_update, name="estimate_update"),
    path("estimates/<int:pk>/delete/", views.estimate_delete, name="estimate_delete"),
    path("estimates/<int:pk>/mark-sent/", views.estimate_mark_sent, name="estimate_mark_sent"),
    path("estimates/<int:pk>/email/", views.estimate_email, name="estimate_email"),
    path("estimates/<int:pk>/convert/", views.estimate_convert, name="estimate_convert"),
    path("estimates/<int:pk>/convert-to-project/", views.estimate_convert_to_project, name="estimate_convert_to_project"),
    path("estimates/<int:pk>/pdf/", views.estimate_pdf, name="estimate_pdf"),

    # Estimates (public)
    path("estimate/p/<uuid:token>/", views.estimate_public, name="estimate_public"),
    path("estimate/p/<uuid:token>/accept/", views.estimate_public_accept, name="estimate_public_accept"),
    path("estimate/p/<uuid:token>/decline/", views.estimate_public_decline, name="estimate_public_decline"),
]
