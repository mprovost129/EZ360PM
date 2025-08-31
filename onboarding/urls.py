from django.urls import path
from . import views

app_name = "onboarding"

urlpatterns = [
    path("", views.start, name="start"),
    path("company/", views.company, name="company"),
    path("client/", views.client, name="client"),
    path("project/", views.project, name="project"),
    path("finish/", views.finish, name="finish"),
]
