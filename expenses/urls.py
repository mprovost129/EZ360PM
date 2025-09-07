# expenses/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "expenses"

urlpatterns = [
    path("", views.expenses_list, name="expenses"),
    path("new/", views.expense_create, name="expense_create"),
    path("<int:pk>/edit/", views.expense_update, name="expense_update"),
    path("<int:pk>/delete/", views.expense_delete, name="expense_delete"),
    path("export.csv", views.expenses_export_csv, name="expenses_export_csv"),
]
