# clients/views.py
from __future__ import annotations

from typing import Dict
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from core.decorators import require_subscription
from company.utils import get_active_company
from .forms import ClientForm
from .models import Client


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _list_url(request: HttpRequest, extra_params: Dict[str, str] | None = None) -> str:
    """
    Return the list URL preserving current query params (e.g., q, page).
    """
    params = {}
    if "q" in request.GET:
        params["q"] = request.GET.get("q", "").strip()
    if "page" in request.GET:
        params["page"] = request.GET.get("page", "").strip()
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v})
    qs = f"?{urlencode(params)}" if params else ""
    return f"/clients/{qs}"  # or: reverse("clients:clients") + qs


# ---------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------
@login_required
@require_subscription
@require_http_methods(["GET"])
def clients_list(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company selected.")
        return redirect("dashboard:home")

    q = (request.GET.get("q") or "").strip()
    qs = Client.objects.filter(company=company)

    if q:
        # Split query into terms and AND them across name/org/email
        terms = [t for t in q.split() if t]
        for t in terms:
            qs = qs.filter(
                Q(org__icontains=t) |
                Q(first_name__icontains=t) |
                Q(last_name__icontains=t) |
                Q(email__icontains=t)
            )

    qs = qs.only(
        "id", "org", "first_name", "last_name", "email", "phone", "created_at"
    ).order_by("-created_at")

    paginator = Paginator(qs, 15)
    clients = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "clients/clients_list.html",
        {"clients": clients, "q": q},
    )


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def client_create(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company selected.")
        return redirect("dashboard:home")

    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            try:
                obj.save()
            except IntegrityError:
                # Mirror the UniqueConstraint (company, email)
                form.add_error("email", "A client with this email already exists for your company.")
            else:
                messages.success(request, "Client created.")
                return redirect(_list_url(request))
    else:
        form = ClientForm()

    return render(request, "clients/client_form.html", {"form": form, "mode": "create"})


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def client_update(request: HttpRequest, pk: int) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company selected.")
        return redirect("dashboard:home")

    obj = get_object_or_404(Client, pk=pk, company=company)

    if request.method == "POST":
        form = ClientForm(request.POST, instance=obj)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error("email", "A client with this email already exists for your company.")
            else:
                messages.success(request, "Client updated.")
                return redirect(_list_url(request))
    else:
        form = ClientForm(instance=obj)

    return render(request, "clients/client_form.html", {"form": form, "mode": "edit", "obj": obj})


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def client_delete(request: HttpRequest, pk: int) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company selected.")
        return redirect("dashboard:home")

    obj = get_object_or_404(Client, pk=pk, company=company)

    if request.method == "POST":
        obj.delete()
        messages.success(request, "Client deleted.")
        return redirect(_list_url(request))

    return render(request, "clients/client_confirm_delete.html", {"obj": obj})
