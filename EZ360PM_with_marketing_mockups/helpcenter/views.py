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



def help_accounts_receivable(request):
    return render(request, "helpcenter/help_accounts_receivable.html", {"shell": _shell_template(request)})


def help_client_credits(request):
    return render(request, "helpcenter/help_client_credits.html", {"shell": _shell_template(request)})


def help_ar_aging(request):
    return render(request, "helpcenter/help_ar_aging.html", {"shell": _shell_template(request)})


def help_collections(request):
    return render(request, "helpcenter/help_collections.html", {"shell": _shell_template(request)})


def help_statements(request):
    return render(request, "helpcenter/help_statements.html", {"shell": _shell_template(request)})


def help_report_interpretation(request):
    return render(request, "helpcenter/help_report_interpretation.html", {"shell": _shell_template(request)})





def help_bills(request):
    return render(request, "helpcenter/help_bills.html", {"shell": _shell_template(request)})


def help_vendor_credits(request):
    return render(request, "helpcenter/help_vendor_credits.html", {"shell": _shell_template(request)})


def help_ap_reconciliation(request):
    return render(request, "helpcenter/help_ap_reconciliation.html", {"shell": _shell_template(request)})


def help_ap_aging(request):
    return render(request, "helpcenter/help_ap_aging.html", {"shell": _shell_template(request)})


def help_storage_files(request):
    return render(request, "helpcenter/help_storage_files.html", {"shell": _shell_template(request)})


def help_billing(request):
    return render(request, "helpcenter/help_billing.html", {"shell": _shell_template(request)})


def help_ops(request):
    # Ops page is staff-only in-app, but docs are public.
    return render(request, "helpcenter/help_ops.html", {"shell": _shell_template(request)})


def help_ops_console(request):
    return render(request, "helpcenter/help_ops_console.html", {"shell": _shell_template(request)})


def help_production_runbook(request):
    return render(request, "helpcenter/help_production_runbook.html", {"shell": _shell_template(request)})


def help_recurring_bills(request):
    return render(request, "helpcenter/help_recurring_bills.html", {"shell": _shell_template(request)})


def help_refunds(request):
    return render(request, "helpcenter/help_refunds.html", {"shell": _shell_template(request)})


def help_faq(request):
    return render(request, "helpcenter/help_faq.html", {"shell": _shell_template(request)})


def help_profit_loss(request):
    return render(request, "helpcenter/help_profit_loss.html", {"shell": _shell_template(request)})


def help_balance_sheet(request):
    return render(request, "helpcenter/help_balance_sheet.html", {"shell": _shell_template(request)})


def help_trial_balance(request):
    return render(request, "helpcenter/help_trial_balance.html", {"shell": _shell_template(request)})


def legal_terms(request):
    return render(
        request,
        "helpcenter/legal_terms.html",
        {"shell": _shell_template(request), "legal_last_updated": "February 18, 2026"},
    )


def legal_privacy(request):
    return render(
        request,
        "helpcenter/legal_privacy.html",
        {"shell": _shell_template(request), "legal_last_updated": "February 18, 2026"},
    )


def legal_cookies(request):
    return render(
        request,
        "helpcenter/legal_cookies.html",
        {"shell": _shell_template(request), "legal_last_updated": "February 18, 2026"},
    )


def legal_acceptable_use(request):
    return render(
        request,
        "helpcenter/legal_acceptable_use.html",
        {"shell": _shell_template(request), "legal_last_updated": "February 18, 2026"},
    )


def legal_security(request):
    return render(
        request,
        "helpcenter/legal_security.html",
        {"shell": _shell_template(request), "legal_last_updated": "February 18, 2026"},
    )


def legal_refund_policy(request):
    return render(
        request,
        "helpcenter/legal_refund_policy.html",
        {"shell": _shell_template(request), "legal_last_updated": "February 18, 2026"},
    )
