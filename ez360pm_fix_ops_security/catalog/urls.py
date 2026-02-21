from __future__ import annotations

from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("catalog/", views.catalog_item_list, name="item_list"),
    path("catalog/new/", views.catalog_item_create, name="item_create"),
    path("catalog/<int:pk>/edit/", views.catalog_item_edit, name="item_edit"),
    path("catalog/<int:pk>/delete/", views.catalog_item_delete, name="item_delete"),
    path("catalog/<int:pk>/json/", views.catalog_item_json, name="item_json"),
]
