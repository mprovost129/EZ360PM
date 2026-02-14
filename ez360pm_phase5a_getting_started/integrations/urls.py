from django.urls import path

from . import views

app_name = "integrations"

urlpatterns = [
    path("integrations/dropbox/", views.dropbox_settings, name="dropbox_settings"),
    path("integrations/dropbox/connect/", views.dropbox_connect, name="dropbox_connect"),
    path("integrations/dropbox/callback/", views.dropbox_callback, name="dropbox_callback"),
    path("integrations/dropbox/disconnect/", views.dropbox_disconnect, name="dropbox_disconnect"),
]
