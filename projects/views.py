# projects/views.py

# --- Stdlib ---
from decimal import Decimal

# --- Third-party / Django ---
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import (
    Q,
    Sum,
    Value,
    DecimalField,
    IntegerField,
    Case,
    When,
)
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from projects.utils import generate_project_number

# --- Local apps ---
# Plan limits (optional; fall back if billing app isn't present)
try:
    from billing.utils import enforce_limit_or_upsell  # type: ignore
except Exception:  # pragma: no cover
    def enforce_limit_or_upsell(company, key: str, current_count: int):
        return True, None

from core.models import Notification
from expenses.models import Expense
from projects.forms import ProjectForm
from projects.models import Project
from timetracking.models import TimeEntry

from core.decorators import require_subscription

from company.services import notify_company
from company.utils import get_active_company


@login_required
def projects_list(request):
    company = get_active_company(request)
    if not company:
        return redirect("onboarding:company")

    q = (request.GET.get("q") or "").strip()
    sort = (request.GET.get("sort") or "recent").lower()
    page = int(request.GET.get("page") or 1)

    qs = (
        Project.objects.filter(company=company)
        .select_related("client")
        .annotate(
            logged_hours=Coalesce(
                Sum("time_entries__hours"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=9, decimal_places=2),
            )
        )
    )

    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(number__icontains=q)
            | Q(client__org__icontains=q)
            | Q(client__first_name__icontains=q)
            | Q(client__last_name__icontains=q)
        )

    if sort == "number":
        qs = qs.order_by("number", "-created_at")
    elif sort == "client":
        qs = qs.order_by(
            "client__org", "client__last_name", "client__first_name", "-created_at"
        )
    elif sort == "due":
        qs = qs.annotate(
            _due_isnull=Case(
                When(due_date__isnull=True, then=1),
                default=0,
                output_field=IntegerField(),
            )
        ).order_by("_due_isnull", "due_date", "-created_at")
    elif sort == "name":
        qs = qs.order_by("name", "-created_at")
    else:
        qs = qs.order_by("-created_at", "-id")

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(page)

    return render(
        request,
        "projects/projects_list.html",
        {
            "projects": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "q": q,
            "sort": sort,
            "today": timezone.localdate(),
        },
    )


@login_required
@require_subscription
def project_create_hourly(request) -> HttpResponse:
    return _project_create(request, default_type=Project.HOURLY)


@login_required
@require_subscription
def project_create_flat(request) -> HttpResponse:
    return _project_create(request, default_type=Project.FLAT)


@login_required
@require_subscription
def _project_create(request, *, default_type: str | int) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.info(request, "Create your company first.")
        return redirect("onboarding:company")

    if callable(enforce_limit_or_upsell):
        count = Project.objects.filter(company=company).count()
        ok, limit = enforce_limit_or_upsell(company, "max_projects", count)
        if not ok:
            messages.warning(
                request,
                f"You've reached your plan’s limit of {limit} projects. Upgrade to add more.",
            )
            return redirect("billing:plans")

    if request.method == "POST":
        form = ProjectForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company

            # Ensure billing_type is set (respect form if present)
            bt = form.cleaned_data.get("billing_type") if "billing_type" in form.fields else None
            obj.billing_type = bt or default_type

            # Assign number if blank, with a small retry to avoid race on UniqueConstraint
            if not (obj.number or "").strip():
                for _ in range(3):  # small retry window
                    obj.number = generate_project_number(company)
                    try:
                        with transaction.atomic():
                            obj.save()
                        break
                    except IntegrityError:
                        continue
                else:
                    messages.error(request, "Couldn’t generate a unique project number. Please try again.")
                    return render(
                        request,
                        "projects/project_form.html",
                        {"form": form, "mode": "create", "default_type": default_type, "company": company},
                    )
            else:
                obj.save()

            # Save M2M after the instance exists
            form.save_m2m()

            try:
                notify_company(
                    company,
                    request.user,
                    f"Project {obj.number or ''} {obj.name} created",
                    url=reverse("projects:project_detail", args=[obj.pk]),
                    kind=Notification.PROJECT_CREATED,
                )
            except Exception:
                pass

            messages.success(request, "Project created.")
            return redirect("projects:project_detail", obj.pk)
    else:
        initial = {"billing_type": default_type}
        form = ProjectForm(initial=initial, company=company)

    return render(
        request,
        "projects/project_form.html",
        {"form": form, "mode": "create", "default_type": default_type, "company": company},
    )



@login_required
@require_subscription
def project_update(request, pk: int):
    company = get_active_company(request)
    obj = get_object_or_404(Project, pk=pk, company=company)
    if request.method == "POST":
        form = ProjectForm(request.POST, instance=obj, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Project updated.")
            return redirect("projects:project_detail", pk=obj.pk)
    else:
        form = ProjectForm(instance=obj, company=company)
    return render(
        request,
        "projects/project_form.html",
        {"form": form, "mode": "edit", "obj": obj},
    )


@login_required
@require_subscription
def project_delete(request, pk: int):
    company = get_active_company(request)
    obj = get_object_or_404(Project, pk=pk, company=company)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Project deleted.")
        return redirect("projects:projects")
    return render(request, "projects/project_confirm_delete.html", {"obj": obj})


@login_required
@require_subscription
def project_detail(request, pk: int):
    company = get_active_company(request)
    obj = get_object_or_404(
        Project.objects.select_related("client"), pk=pk, company=company
    )

    active = (
        TimeEntry.objects.filter(project=obj, user=request.user, end_time__isnull=True)
        .order_by("-start_time")
        .first()
    )

    total_hours = (
        TimeEntry.objects.filter(project=obj).aggregate(s=Sum("hours")).get("s") or 0
    )
    unbilled_hours = (
        TimeEntry.objects.filter(project=obj, invoice__isnull=True)
        .aggregate(s=Sum("hours"))
        .get("s")
        or 0
    )
    unbilled_expenses_count = Expense.objects.filter(
        project=obj, is_billable=True, invoice__isnull=True
    ).count()

    time_entries = obj.time_entries.all().order_by("-start_time", "-id")  # type: ignore

    return render(
        request,
        "projects/project_detail.html",
        {
            "obj": obj,
            "active": active,
            "total_hours": total_hours,
            "unbilled_hours": unbilled_hours,
            "unbilled_expenses_count": unbilled_expenses_count,
            "time_entries": time_entries,
        },
    )
