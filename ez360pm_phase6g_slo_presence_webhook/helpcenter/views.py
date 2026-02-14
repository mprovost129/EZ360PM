from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def _shell_template(request) -> str:
    """Render help/legal into the most appropriate shell."""
    if request.user.is_authenticated:
        return "helpcenter/_help_shell_app.html"
    return "helpcenter/_help_shell_public.html"


def help_home(request):
    return render(request, "helpcenter/help_home.html", {"shell": _shell_template(request)})


def help_getting_started(request):
    return render(request, "helpcenter/help_getting_started.html", {"shell": _shell_template(request)})


def help_roles_permissions(request):
    return render(request, "helpcenter/help_roles_permissions.html", {"shell": _shell_template(request)})


def help_time_tracking(request):
    return render(request, "helpcenter/help_time_tracking.html", {"shell": _shell_template(request)})


def help_invoices_payments(request):
    return render(request, "helpcenter/help_invoices_payments.html", {"shell": _shell_template(request)})


def help_accounting(request):
    return render(request, "helpcenter/help_accounting.html", {"shell": _shell_template(request)})


def help_storage_files(request):
    return render(request, "helpcenter/help_storage_files.html", {"shell": _shell_template(request)})


def help_billing(request):
    return render(request, "helpcenter/help_billing.html", {"shell": _shell_template(request)})


def help_ops(request):
    # Ops page is staff-only in-app, but docs are public.
    return render(request, "helpcenter/help_ops.html", {"shell": _shell_template(request)})


def help_faq(request):
    return render(request, "helpcenter/help_faq.html", {"shell": _shell_template(request)})


def legal_terms(request):
    return render(request, "helpcenter/legal_terms.html", {"shell": _shell_template(request)})


def legal_privacy(request):
    return render(request, "helpcenter/legal_privacy.html", {"shell": _shell_template(request)})


def legal_cookies(request):
    return render(request, "helpcenter/legal_cookies.html", {"shell": _shell_template(request)})


def legal_acceptable_use(request):
    return render(request, "helpcenter/legal_acceptable_use.html", {"shell": _shell_template(request)})


def legal_security(request):
    return render(request, "helpcenter/legal_security.html", {"shell": _shell_template(request)})


def legal_refund_policy(request):
    return render(request, "helpcenter/legal_refund_policy.html", {"shell": _shell_template(request)})
