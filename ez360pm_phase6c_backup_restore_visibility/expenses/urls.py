from django.urls import path

from . import views

app_name = "expenses"

urlpatterns = [
    path("expenses/", views.expense_list, name="expense_list"),
    path("expenses/new/", views.expense_create, name="expense_create"),
    path("expenses/<uuid:pk>/edit/", views.expense_edit, name="expense_edit"),
    path("expenses/<uuid:pk>/delete/", views.expense_delete, name="expense_delete"),
    path("merchants/", views.merchant_list, name="merchant_list"),
    path("merchants/new/", views.merchant_create, name="merchant_create"),
]
