# onboarding/urls.py
from django.urls import path
from . import views

app_name = "onboarding"

urlpatterns = [
    # Entry point: decide where to send user
    path("", views.start, name="start"),

    # Wizard steps
    path("company/", views.company, name="company"),   # required
    path("client/", views.client, name="client"),     # optional, skippable
    path("project/", views.project, name="project"),  # optional, skippable
    
    path("payments/", views.payments, name="payments"),
    path("team/", views.team, name="team"),

    # Completion
    path("finish/", views.finish, name="finish"),
]
