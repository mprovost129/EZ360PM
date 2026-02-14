from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<uuid:pk>/", views.project_detail, name="project_detail"),
    path("projects/<uuid:pk>/files/", views.project_files, name="project_files"),
    path("projects/<uuid:pk>/files/sync-dropbox/", views.project_files_sync_dropbox, name="project_files_sync_dropbox"),
    path("projects/<uuid:pk>/files/<uuid:file_id>/open/", views.project_file_open, name="project_file_open"),
    path("projects/<uuid:pk>/files/<uuid:file_id>/download/", views.project_file_open, name="project_file_download"),
    path("projects/<uuid:pk>/files/<uuid:file_id>/delete/", views.project_file_delete, name="project_file_delete"),
    path("projects/<uuid:pk>/edit/", views.project_edit, name="project_edit"),
    path("projects/<uuid:pk>/delete/", views.project_delete, name="project_delete"),
]
