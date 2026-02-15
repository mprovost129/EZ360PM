from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    path("clients/", views.client_list, name="client_list"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clients/import/", views.client_import, name="client_import"),
    path("clients/import/<uuid:batch_id>/map/", views.client_import_map, name="client_import_map"),
    path("clients/import/<uuid:batch_id>/done/", views.client_import_done, name="client_import_done"),
    path("clients/import/<uuid:batch_id>/report.csv", views.client_import_report_download, name="client_import_report_download"),
    path("clients/export/", views.client_export, name="client_export"),
    path("clients/<uuid:pk>/edit/", views.client_edit, name="client_edit"),
    path("clients/<uuid:pk>/delete/", views.client_delete, name="client_delete"),
]
