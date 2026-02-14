from django.urls import path

from core import views_storage


app_name = "storage"


urlpatterns = [
    path("api/v1/storage/presign/", views_storage.presign_upload, name="presign_upload"),
]
