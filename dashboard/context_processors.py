from .utils import get_cookie_consent

def cookie_consent(request):
    consent = get_cookie_consent(request)
    return {"cookie_consent": consent}
