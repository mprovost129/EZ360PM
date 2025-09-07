# clients/urls.py
from django.urls import path
from . import views

app_name = "clients"

urlpatterns = [
    # List & detail
    path("", views.clients_list, name="clients"),
    # path("<int:pk>/", views.client_detail, name="detail"),  # optional

    # CRUD
    path("create/", views.client_create, name="client_create"),
    path("<int:pk>/edit/", views.client_update, name="edit"),
    path("<int:pk>/delete/", views.client_delete, name="delete"),
]
