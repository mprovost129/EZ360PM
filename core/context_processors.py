# core/context_processors.py
from .utils import get_active_company, user_has_active_subscription
from .models import Notification
from django.conf import settings
from .services import unread_count


def active_company(request):
    return {"active_company": get_active_company(request)}


def notifications(request):
    if not request.user.is_authenticated:
        return {"unread_notifications_count": 0}
    company = get_active_company(request)
    if not company:
        return {"unread_notifications_count": 0}
    count = Notification.objects.filter(company=company, recipient=request.user, read_at__isnull=True).count()
    return {"unread_notifications_count": count}

def branding(_request):
    return {"APP_NAME": getattr(settings, "APP_NAME", "EZ360PM")}

def active_and_notifications(request):
    c = get_active_company(request)
    cnt = 0
    if request.user.is_authenticated and c:
        cnt = unread_count(c, request.user)
    return {"active_company": c, "unread_notifications_count": cnt}


def app_context(request):
    company = None
    subscribed = False
    try:
        if request.user.is_authenticated:
            company = get_active_company(request)
            if company:
                subscribed = user_has_active_subscription(company)
    except Exception:
        pass
    return {
        "active_company": company,
        "is_subscribed": subscribed,
    }
    

def app_frame(request):
    user = request.user
    active_company = None
    unread_notifications_count = 0

    if getattr(user, "is_authenticated", False):
        try:
            active_company = get_active_company(request)
        except Exception:
            active_company = None
        if active_company:
            try:
                unread_notifications_count = (
                    Notification.objects.for_company_user(active_company, user) # type: ignore
                    .unread()
                    .count()
                )
            except Exception:
                unread_notifications_count = 0

    return {
        "active_company": active_company,
        "unread_notifications_count": unread_notifications_count,
    }
    
def app_globals(request):
    return {
        "APP_NAME": getattr(settings, "APP_NAME", "EZ360PM"),
        "company_name": getattr(settings, "COMPANY_NAME", "EZ360PM, LLC"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", "support@example.com"),
        "do_not_sell_url": getattr(settings, "DO_NOT_SELL_URL", ""),
        # also handy for the cookie banner/analytics
        "COOKIE_CONSENT_NAME": getattr(settings, "COOKIE_CONSENT_NAME", "cookie_consent"),
        "PLAUSIBLE_DOMAIN": getattr(settings, "PLAUSIBLE_DOMAIN", ""),
        "GA_MEASUREMENT_ID": getattr(settings, "GA_MEASUREMENT_ID", ""),
    }