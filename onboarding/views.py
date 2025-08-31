from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from core.forms import CompanyForm, ClientForm, ProjectForm
from core.models import CompanyMember, Client, Project
from core.utils import (
    get_active_company,
    set_active_company,
    get_user_profile,
)
from core.decorators import require_subscription  # keep handy if you gate later

@login_required
def start(request):
    """
    Decide where to send the user when they enter the wizard.
    If they already have an active company, skip straight to next step.
    """
    company = get_active_company(request)
    if company:
        return redirect("onboarding:client")
    return redirect("onboarding:company")


@login_required
def company(request):
    """
    Create or pick the first company. This step is required to proceed.
    """
    company = get_active_company(request)
    if company:
        # If they already have one, skip
        return redirect("onboarding:client")

    if request.method == "POST":
        form = CompanyForm(request.POST, request.FILES)
        if form.is_valid():
            c = form.save(commit=False)
            c.owner = request.user
            c.save()
            CompanyMember.objects.get_or_create(
                company=c, user=request.user,
                defaults={"role": CompanyMember.OWNER}
            )
            set_active_company(request, c)
            messages.success(request, "Company created.")
            return redirect("onboarding:client")
    else:
        # Nice default name
        default_name = (getattr(request.user, "name", "") or request.user.email).strip()
        form = CompanyForm(initial={"name": f"{default_name} — Company"})

    return render(request, "onboarding/company.html", {"form": form})


@login_required
def client(request):
    """
    Optional: add first client. Skippable.
    """
    company = get_active_company(request)
    if not company:
        return redirect("onboarding:company")

    if request.method == "POST":
        if "skip" in request.POST:
            return redirect("onboarding:project")
        form = ClientForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Client added.")
            return redirect("onboarding:project")
    else:
        form = ClientForm()

    return render(request, "onboarding/client.html", {"form": form})


@login_required
def project(request):
    """
    Optional: add first project. Skippable.
    """
    company = get_active_company(request)
    if not company:
        return redirect("onboarding:company")

    if request.method == "POST":
        if "skip" in request.POST:
            return redirect("onboarding:finish")
        form = ProjectForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            form.save_m2m()
            messages.success(request, "Project created.")
            return redirect("onboarding:finish")
    else:
        form = ProjectForm()

    return render(request, "onboarding/project.html", {"form": form})


@login_required
def finish(request):
    """
    Mark onboarding complete and go to dashboard.
    """
    profile = get_user_profile(request.user)
    if not getattr(profile, "onboarded", None):
        # Add a simple flag if your profile has it; otherwise this is harmless.
        try:
            profile.onboarded = True  # type: ignore[attr-defined]
            profile.save(update_fields=["onboarded"])
        except Exception:
            pass

    messages.success(request, "All set! Welcome to your dashboard.")
    return redirect("dashboard:home")
