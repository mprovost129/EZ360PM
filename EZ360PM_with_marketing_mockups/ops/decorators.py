from django.contrib.auth.decorators import user_passes_test
from functools import wraps
from django.http import HttpResponseForbidden


def staff_only(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return HttpResponseForbidden("Staff only.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view
