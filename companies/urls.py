from django.urls import path

from . import views


app_name = "companies"


urlpatterns = [
    path("onboarding/", views.onboarding, name="onboarding"),
    path("switch/", views.switch_company, name="switch"),
    path("switch/set/", views.set_active_company, name="set_active"),
    path("settings/", views.company_settings, name="settings"),
    path("team/", views.team_list, name="team_list"),
    path("team/invite/", views.invite_create, name="invite_create"),
    path("invite/<str:token>/", views.invite_accept, name="invite_accept"),
    path("team/invite/<uuid:invite_id>/resend/", views.invite_resend, name="invite_resend"),
    path("team/invite/<uuid:invite_id>/revoke/", views.invite_revoke, name="invite_revoke"),
    path("team/employee/<int:employee_id>/unlock/", views.employee_unlock, name="employee_unlock"),
    path("suspended/", views.account_suspended, name="account_suspended"),
]
