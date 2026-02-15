from django.urls import path

from . import views
from . import views_support


app_name = "core"


urlpatterns = [
    path("", views.home, name="home"),
    path("app/", views.app_dashboard, name="app_dashboard"),
    path("getting-started/", views.getting_started, name="getting_started"),
    path("health/", views.health, name="health"),

    path("support/mode/", views_support.support_mode_status, name="support_mode_status"),
    path("support/mode/enter/", views_support.support_mode_enter, name="support_mode_enter"),
    path("support/mode/exit/", views_support.support_mode_exit, name="support_mode_exit"),
]
