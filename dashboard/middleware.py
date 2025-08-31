# dashboard/middleware.py
from django.shortcuts import redirect
from django.urls import resolve, reverse
from core.utils import get_active_company, get_onboarding_status

class OnboardingRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                match = resolve(request.path_info)
            except Exception:
                return self.get_response(request)

            if match.view_name == "dashboard:home" and not request.session.get("onboarding_dismissed"):
                company = get_active_company(request)
                status = get_onboarding_status(request.user, company)
                if not status["complete"] and match.view_name != "dashboard:onboarding":
                    return redirect("dashboard:onboarding")

        return self.get_response(request)
