# core/views_onboarding.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect

from .forms import CompanyForm
from .utils import get_user_companies, set_active_company


@login_required(login_url="accounts:login")
def onboarding_company(request: HttpRequest) -> HttpResponse:
    """
    Onboarding step: prompt a new user to create their first Company.
    If the user already has one, skip to dashboard.
    """
    if get_user_companies(request.user).exists():  # type: ignore[attr-defined]
        messages.info(request, "You already have a company.")
        return redirect("dashboard:home")

    if request.method == "POST":
        form = CompanyForm(request.POST, request.FILES)
        if form.is_valid():
            company = form.save(commit=False)
            company.owner = request.user
            company.save()
            set_active_company(request, company)
            messages.success(request, f"Welcome to {company.name}!")
            return redirect("dashboard:home")
    else:
        form = CompanyForm()

    return render(request, "core/onboarding_company.html", {"form": form})
