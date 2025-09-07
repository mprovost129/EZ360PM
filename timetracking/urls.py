# timetracking/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "timetracking"

urlpatterns = [
    # Ajax/API for topbar timer
    path("timer/status/", views.timer_status, name="timer_status"),
    path("timer/start/", views.timer_start, name="timer_start"),
    path("timer/stop/", views.timer_stop, name="timer_stop"),
    path("timer/save/", views.timer_save, name="timer_save"),
    path("timer/delete/<str:pk>/", views.timer_delete, name="timer_delete"),

    # Pages
    path("time/", views.time_list, name="time_list"),
    path("project/<int:pk>/timer/start/", views.project_timer_start, name="project_timer_start"),
    path("project/<int:pk>/timer/stop/", views.project_timer_stop, name="project_timer_stop"),
    path("project/<int:pk>/time/new/", views.timeentry_create, name="timeentry_create"),
    path("timesheets/week/", views.timesheet_week, name="timesheet_week"),
    path("timesheets/submit/", views.timesheet_submit_week, name="timesheet_submit_week"),
    path("approvals/", views.approvals_list, name="approvals_list"),
    path("approvals/decide/", views.approvals_decide, name="approvals_decide"),
]