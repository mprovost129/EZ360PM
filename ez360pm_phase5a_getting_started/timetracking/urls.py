from django.urls import path

from . import views

app_name = "timetracking"

urlpatterns = [
    path("time/", views.time_entry_list, name="entry_list"),
    path("time/new/", views.time_entry_create, name="entry_create"),
    path("time/<uuid:pk>/", views.time_entry_detail, name="entry_detail"),
    path("time/<uuid:pk>/edit/", views.time_entry_edit, name="entry_edit"),
    path("time/<uuid:pk>/delete/", views.time_entry_delete, name="entry_delete"),

    path("time/<uuid:pk>/submit/", views.time_entry_submit, name="entry_submit"),
    path("time/<uuid:pk>/approve/", views.time_entry_approve, name="entry_approve"),

    path("time/settings/", views.time_settings, name="settings"),

    # timer (single global timer per employee)
    path("time/timer/", views.timer_panel, name="timer_panel"),
    path("time/timer/start/", views.timer_start, name="timer_start"),
    path("time/timer/stop/", views.timer_stop, name="timer_stop"),
]
