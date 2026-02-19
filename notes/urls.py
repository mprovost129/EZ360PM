from django.urls import path

from notes import views

app_name = "notes"

urlpatterns = [
    path("notes/", views.note_list, name="list"),
    path("notes/create/", views.note_create, name="create"),
    path("notes/<int:pk>/delete/", views.note_delete, name="delete"),
]
