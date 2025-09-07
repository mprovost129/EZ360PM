# payments/views.py
from __future__ import annotations

# --- Third-party / Django ---
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

# --- Local apps ---
from invoices.models import Invoice
from invoices.services import recalc_invoice

from core.decorators import require_subscription
from payments.forms import PaymentForm
from core.models import Notification
from company.services import notify_company
from company.utils import get_active_company


@login_required
@require_subscription
def payments_list(request):
    return render(request, "payments/payments_list.html")


@login_required
@require_subscription
def payment_create(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(Invoice, pk=pk, company=company)
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            p = form.save(commit=False)
            notify_company(
                company,
                request.user,
                f"Payment {p.amount} recorded for invoice {inv.number}",
                url=reverse("invoices:invoice_detail", args=[inv.pk]),
                kind=Notification.INVOICE_PAID,
            )
            p.company = company
            p.invoice = inv
            p.save()
            recalc_invoice(inv)
            messages.success(request, "Payment recorded.")
            return redirect("invoices:invoice_detail", pk=pk)
    else:
        form = PaymentForm()
    return render(request, "payments/payment_form.html", {"form": form, "inv": inv})