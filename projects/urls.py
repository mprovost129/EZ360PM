# projects/urls.py
from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("projects/", views.projects_list, name="projects"),
    path("projects/new/hourly/", views.project_create_hourly, name="project_create_hourly"),
    path("projects/new/flat/", views.project_create_flat, name="project_create_flat"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/edit/", views.project_update, name="project_update"),
    path("projects/<int:pk>/delete/", views.project_delete, name="project_delete"),
]