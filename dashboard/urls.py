# dashboard/urls.py
from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    # ---- Home ----
    path("", views.home, name="home"),

    # ---- Contact / Suggestions ----
    path("contact/submit/", views.contact_submit, name="contact_submit"),
    path("contact/", views.contact, name="contact"),
    path("contact/thanks/", views.contact_thanks, name="contact_thanks"),

    # ---- Help Center ----
    path("help/", views.help_index, name="help_index"),
    path("help/<slug:slug>/", views.help_article, name="help_article"),

    # ---- Onboarding ----
    path("onboarding/", views.onboarding, name="onboarding"),
    path("onboarding/dismiss/", views.onboarding_dismiss, name="onboarding_dismiss"),

    # ---- Legal / Policies ----
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("legal/subprocessors/", views.subprocessors, name="subprocessors"),
    path("legal/cookies/", views.cookies, name="cookies"),
    path("legal/cookies/preferences/", views.cookie_preferences, name="cookie_preferences"),
    path("legal/cookies/set/", views.cookie_consent_set, name="cookie_consent_set"),
]
