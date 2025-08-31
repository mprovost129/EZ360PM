# core/views_onboarding.py (or keep in core/views.py if you prefer)
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from .forms import CompanyForm
from .utils import get_user_companies, set_active_company

@login_required
def onboarding_company(request):
    if get_user_companies(request.user).exists(): # type: ignore
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
