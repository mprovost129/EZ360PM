# company/urls.py
from __future__ import annotations

from django.urls import path
from . import views
from .views_onboarding import onboarding_company

app_name = "company"

urlpatterns = [
    # Company profile & settings
    path("", views.company_profile, name="company_profile"),
    path("edit/", views.company_edit, name="company_edit"),
    path("new/", views.company_create, name="company_create"),
    path("switch/<int:company_id>/", views.company_switch, name="company_switch"),

    # Team management
    path("team/", views.team_list, name="team_list"),
    path("team/invite/", views.invite_create, name="invite_create"),
    path("team/members/<int:member_id>/edit/", views.member_edit, name="member_edit"),
    path("team/members/<int:member_id>/remove/", views.member_remove, name="member_remove"),

    # Invites
    path("invite/<uuid:token>/", views.invite_accept, name="invite_accept"),

    # Onboarding
    path("onboarding/company/", onboarding_company, name="onboarding_company"),
]
