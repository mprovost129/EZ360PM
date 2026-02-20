from __future__ import annotations

from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Any

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from audit.services import log_event
from companies.decorators import company_context_required, require_min_role
from companies.models import EmployeeRole

from billing.decorators import tier_required
from billing.models import PlanCode
from billing.services import build_subscription_summary, plan_meets
from projects.models import Project
from crm.models import Client

from .forms import TimeEntryForm, TimeEntryServiceFormSet, TimeFilterForm, TimerStartForm, TimeSettingsForm
from .models import TimeEntry, TimeEntryService, TimeStatus, TimerState, TimeTrackingSettings

from .services_timer import clear_timer_defaults, get_timer_state, persist_timer_defaults

from core.pagination import paginate


def _timer_total_seconds(timer_state: TimerState, now) -> int:
    total = int(timer_state.elapsed_seconds or 0)
    if timer_state.is_running and timer_state.started_at and not getattr(timer_state, "is_paused", False):
        total += max(0, int((now - timer_state.started_at).total_seconds()))
    return max(0, int(total))


def _preset_dates(preset: str) -> tuple[date | None, date | None]:
    today = timezone.localdate()
    if preset == "today":
        return today, today
    if preset == "yesterday":
        y = today - timedelta(days=1)
        return y, y
    if preset == "last7":
        return today - timedelta(days=6), today
    if preset == "thismonth":
        start = today.replace(day=1)
        return start, today
    if preset == "lastmonth":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        start_prev = last_prev.replace(day=1)
        return start_prev, last_prev
    return None, None


def _qs_for_employee(request) -> Any:
    company = request.active_company
    employee = request.active_employee
    qs = (
        TimeEntry.objects.filter(company=company, deleted_at__isnull=True)
        .select_related("client", "project", "employee", "approved_by")
        .prefetch_related("services")
        .order_by("-started_at", "-created_at")
    )
    if employee.role == EmployeeRole.STAFF:
        qs = qs.filter(employee=employee)
    return qs


@company_context_required
def time_entry_list(request):
    company = request.active_company
    employee = request.active_employee

    form = TimeFilterForm(request.GET or None)
    qs = _qs_for_employee(request)

    preset = (request.GET.get("preset") or "last7").strip()
    start, end = _preset_dates(preset)

    if form.is_valid():
        q = (form.cleaned_data.get("q") or "").strip()
        status = (form.cleaned_data.get("status") or "").strip()
        billable = (form.cleaned_data.get("billable") or "").strip()

        start = form.cleaned_data.get("start") or start
        end = form.cleaned_data.get("end") or end

        if q:
            qs = qs.filter(
                Q(note__icontains=q)
                | Q(project__name__icontains=q)
                | Q(project__project_number__icontains=q)
                | Q(client__company_name__icontains=q)
                | Q(client__last_name__icontains=q)
                | Q(client__first_name__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)
        if billable in {"0", "1"}:
            qs = qs.filter(billable=(billable == "1"))

    if start:
        qs = qs.filter(started_at__date__gte=start)
    if end:
        qs = qs.filter(started_at__date__lte=end)

    totals = qs.aggregate(total_minutes=Sum("duration_minutes"))
    total_minutes = int(totals.get("total_minutes") or 0)

    # timer state (single global timer)
    timer_state = get_timer_state(company=company, employee=employee)
    timer_running = bool(timer_state.is_running and (timer_state.started_at or timer_state.elapsed_seconds))

    paged = paginate(request, qs)

    return render(
        request,
        "timetracking/time_list.html",
        {
            "filter_form": form,
            "entries": paged.object_list,
            "paginator": paged.paginator,
            "page_obj": paged.page_obj,
            "per_page": paged.per_page,
            "total_minutes": total_minutes,
            "timer_state": timer_state,
            "timer_running": timer_running,
        },
    )


@company_context_required
def time_entry_detail(request, pk):
    company = request.active_company
    employee = request.active_employee

    entry = get_object_or_404(TimeEntry, pk=pk, company=company, deleted_at__isnull=True)

    if employee.role == EmployeeRole.STAFF and entry.employee_id != employee.id:
        messages.error(request, "You do not have access to that time entry.")
        return redirect("timetracking:entry_list")

    return render(request, "timetracking/time_detail.html", {"entry": entry})


@company_context_required
def time_entry_create(request):
    company = request.active_company
    employee = request.active_employee

    # Staff can create their own entries; managers can create for anyone later (v1: self only)
    if request.method == "POST":
        form = TimeEntryForm(request.POST)
        formset = TimeEntryServiceFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                entry: TimeEntry = form.save(commit=False)
                entry.company = company
                entry.employee = employee
                entry.status = TimeStatus.DRAFT
                entry.updated_by_user = request.user
                entry.save()

                formset.instance = entry
                formset.save()

                log_event(
                    company=company,
                    actor=employee,
                    event_type="time.created",
                    object_type="TimeEntry",
                    object_id=entry.id,
                    summary="Created time entry",
                    payload={"status": entry.status, "duration_minutes": entry.duration_minutes},
                    request=request,
                )

                messages.success(request, "Time entry created.")
                return redirect("timetracking:entry_detail", pk=entry.pk)
    else:
        form = TimeEntryForm()
        formset = TimeEntryServiceFormSet()

    return render(request, "timetracking/time_form.html", {"form": form, "formset": formset, "mode": "create"})


@company_context_required
def time_entry_edit(request, pk):
    company = request.active_company
    employee = request.active_employee

    entry = get_object_or_404(TimeEntry, pk=pk, company=company, deleted_at__isnull=True)

    if employee.role == EmployeeRole.STAFF and entry.employee_id != employee.id:
        messages.error(request, "You do not have access to that time entry.")
        return redirect("timetracking:entry_list")

    if entry.status in {TimeStatus.APPROVED, TimeStatus.BILLED} and employee.role == EmployeeRole.STAFF:
        messages.error(request, "Approved/billed time cannot be edited by staff.")
        return redirect("timetracking:entry_detail", pk=entry.pk)

    if request.method == "POST":
        form = TimeEntryForm(request.POST, instance=entry)
        formset = TimeEntryServiceFormSet(request.POST, instance=entry)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                entry = form.save(commit=False)
                entry.updated_by_user = request.user
                entry.save()
                formset.save()

                log_event(
                    company=company,
                    actor=employee,
                    event_type="time.updated",
                    object_type="TimeEntry",
                    object_id=entry.id,
                    summary="Updated time entry",
                    payload={"status": entry.status, "duration_minutes": entry.duration_minutes},
                    request=request,
                )

                messages.success(request, "Time entry updated.")
                return redirect("timetracking:entry_detail", pk=entry.pk)
    else:
        form = TimeEntryForm(instance=entry)
        formset = TimeEntryServiceFormSet(instance=entry)

    return render(request, "timetracking/time_form.html", {"form": form, "formset": formset, "mode": "edit", "entry": entry})


@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def time_entry_delete(request, pk):
    company = request.active_company
    employee = request.active_employee

    entry = get_object_or_404(TimeEntry, pk=pk, company=company, deleted_at__isnull=True)

    if request.method == "POST":
        entry.deleted_at = timezone.now()
        entry.updated_by_user = request.user
        entry.save(update_fields=["deleted_at", "updated_at", "updated_by_user"])

        log_event(
            company=company,
            actor=employee,
            event_type="time.deleted",
            object_type="TimeEntry",
            object_id=entry.id,
            summary="Deleted time entry",
            payload={},
            request=request,
        )
        messages.success(request, "Time entry deleted.")
        return redirect("timetracking:entry_list")

    return render(request, "timetracking/time_delete.html", {"entry": entry})


@company_context_required
def time_entry_submit(request, pk):
    company = request.active_company
    employee = request.active_employee

    entry = get_object_or_404(TimeEntry, pk=pk, company=company, deleted_at__isnull=True)
    if entry.employee_id != employee.id and employee.role == EmployeeRole.STAFF:
        messages.error(request, "You can only submit your own time.")
        return redirect("timetracking:entry_list")

    if request.method == "POST":
        # If settings require approval, go to submitted; else approve immediately for managers/admins/owner.
        settings = TimeTrackingSettings.objects.filter(company=company, employee=employee).first()
        require_approval = bool(settings.require_manager_approval) if settings else False

        # Manager approval workflow is a Professional+ feature.
        summary = build_subscription_summary(company)
        if not plan_meets(summary.plan, min_plan=PlanCode.PROFESSIONAL):
            require_approval = False

        if require_approval:
            entry.status = TimeStatus.SUBMITTED
        else:
            entry.status = TimeStatus.APPROVED
            entry.approved_by = employee
            entry.approved_at = timezone.now()

        entry.updated_by_user = request.user
        entry.save()

        log_event(
            company=company,
            actor=employee,
            event_type="time.submitted",
            object_type="TimeEntry",
            object_id=entry.id,
            summary="Submitted time entry",
            payload={"status": entry.status},
            request=request,
        )

        messages.success(request, f"Time entry marked as {entry.get_status_display()}.")
        return redirect("timetracking:entry_detail", pk=entry.pk)

    return redirect("timetracking:entry_detail", pk=entry.pk)


@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.MANAGER)
def time_entry_approve(request, pk):
    company = request.active_company
    employee = request.active_employee

    entry = get_object_or_404(TimeEntry, pk=pk, company=company, deleted_at__isnull=True)
    if request.method == "POST":
        entry.status = TimeStatus.APPROVED
        entry.approved_by = employee
        entry.approved_at = timezone.now()
        entry.updated_by_user = request.user
        entry.save()

        log_event(
            company=company,
            actor=employee,
            event_type="time.approved",
            object_type="TimeEntry",
            object_id=entry.id,
            summary="Approved time entry",
            payload={},
            request=request,
        )

        messages.success(request, "Time entry approved.")
    return redirect("timetracking:entry_detail", pk=entry.pk)


@company_context_required
def time_settings(request):
    company = request.active_company
    employee = request.active_employee

    settings_obj, _ = TimeTrackingSettings.objects.get_or_create(company=company, employee=employee)

    summary = build_subscription_summary(company)
    can_require_approval = plan_meets(summary.plan, min_plan=PlanCode.PROFESSIONAL)
    if request.method == "POST":
        form = TimeSettingsForm(request.POST, instance=settings_obj)
        if not can_require_approval:
            form.fields.pop("require_manager_approval", None)
        if form.is_valid():
            s = form.save(commit=False)
            if not can_require_approval:
                s.require_manager_approval = False
            s.updated_by_user = request.user
            s.save()
            messages.success(request, "Time tracking settings saved.")
            return redirect("timetracking:settings")
    else:
        form = TimeSettingsForm(instance=settings_obj)
        if not can_require_approval:
            form.fields.pop("require_manager_approval", None)

    return render(request, "timetracking/time_settings.html", {"form": form})


@company_context_required
def timer_panel(request):
    company = request.active_company
    employee = request.active_employee

    can_manage_catalog = bool(employee and employee.role in {"owner", "admin", "manager"})
    timer_state = get_timer_state(company=company, employee=employee)

    form = TimerStartForm(
        company=company,
        initial={
            "project": timer_state.project_id,
            "service_catalog_item": timer_state.service_catalog_item_id,
            "service_name": timer_state.service_name,
            "note": timer_state.note,
        },
    )
    return render(
        request,
        "timetracking/timer_panel.html",
        {"timer_state": timer_state, "form": form, "can_manage_catalog": can_manage_catalog},
    )


@company_context_required
def timer_start(request):
    company = request.active_company
    employee = request.active_employee

    timer_state = get_timer_state(company=company, employee=employee)

    if request.method != "POST":
        return redirect("timetracking:timer_panel")

    can_manage_catalog = bool(request.active_employee and request.active_employee.role in {"owner", "admin", "manager"})
    form = TimerStartForm(request.POST, company=company, can_manage_catalog=can_manage_catalog)
    if not form.is_valid():
        messages.error(request, "Please correct the timer form.")
        return render(request, "timetracking/timer_panel.html", {"timer_state": timer_state, "form": form})

    timer_state.project = form.cleaned_data.get("project")
    # Client is derived from project (no separate selection in UI).
    timer_state.client = timer_state.project.client if timer_state.project else None
    timer_state.service_catalog_item = form.cleaned_data.get("service_catalog_item")
    timer_state.service_name = (form.cleaned_data.get("service_name") or "").strip()

    # Optional: create a new catalog service on the fly (Manager+ only).
    save_to_catalog = bool(form.cleaned_data.get("save_service_to_catalog"))
    if save_to_catalog and can_manage_catalog and not timer_state.service_catalog_item and timer_state.service_name:
        from catalog.models import CatalogItem, CatalogItemType, TaxBehavior

        created_service, _ = CatalogItem.objects.get_or_create(
            company=company,
            item_type=CatalogItemType.SERVICE,
            name=timer_state.service_name,
            defaults={
                "unit_price_cents": 0,
                "tax_behavior": TaxBehavior.NON_TAXABLE,
                "is_active": True,
            },
        )
        timer_state.service_catalog_item = created_service
        timer_state.service_name = ""
    timer_state.note = form.cleaned_data.get("note") or ""
    timer_state.is_running = True
    timer_state.is_paused = False
    timer_state.paused_at = None
    timer_state.elapsed_seconds = 0
    timer_state.started_at = timezone.now()
    timer_state.updated_by_user = request.user
    timer_state.save()

    # Persist last selections so they survive TimerState recreation.
    persist_timer_defaults(company=company, employee=employee, timer_state=timer_state)

    log_event(
        company=company,
        actor=employee,
        event_type="timer.started",
        object_type="TimerState",
        object_id=timer_state.id,
        summary="Started timer",
        payload={
            "project_id": str(timer_state.project_id or ""),
            "client_id": str(timer_state.client_id or ""),
            "service_catalog_item_id": str(timer_state.service_catalog_item_id or ""),
            "service_name": timer_state.service_name,
        },
        request=request,
    )

    messages.success(request, "Timer started.")
    return redirect("timetracking:entry_list")


@company_context_required
def timer_pause(request):
    company = request.active_company
    employee = request.active_employee

    timer_state = get_timer_state(company=company, employee=employee)
    if request.method != "POST":
        return redirect("timetracking:entry_list")

    if not timer_state.is_running or not timer_state.started_at or timer_state.is_paused:
        return redirect("timetracking:entry_list")

    now = timezone.now()
    timer_state.elapsed_seconds = _timer_total_seconds(timer_state, now)
    timer_state.is_paused = True
    timer_state.paused_at = now
    timer_state.updated_by_user = request.user
    timer_state.save()

    log_event(
        company=company,
        actor=employee,
        event_type="timer.paused",
        object_type="TimerState",
        object_id=timer_state.id,
        summary="Paused timer",
        payload={"elapsed_seconds": int(timer_state.elapsed_seconds or 0)},
        request=request,
    )

    return redirect(request.META.get("HTTP_REFERER") or "timetracking:entry_list")


@company_context_required
def timer_resume(request):
    company = request.active_company
    employee = request.active_employee

    timer_state = get_timer_state(company=company, employee=employee)
    if request.method != "POST":
        return redirect("timetracking:entry_list")

    if not timer_state.is_running or not timer_state.is_paused:
        return redirect("timetracking:entry_list")

    now = timezone.now()
    # Keep elapsed_seconds as-is; restart the active segment.
    timer_state.started_at = now
    timer_state.is_paused = False
    timer_state.paused_at = None
    timer_state.updated_by_user = request.user
    timer_state.save()

    log_event(
        company=company,
        actor=employee,
        event_type="timer.resumed",
        object_type="TimerState",
        object_id=timer_state.id,
        summary="Resumed timer",
        payload={"elapsed_seconds": int(timer_state.elapsed_seconds or 0)},
        request=request,
    )

    return redirect(request.META.get("HTTP_REFERER") or "timetracking:entry_list")


@company_context_required
def timer_stop(request):
    company = request.active_company
    employee = request.active_employee

    timer_state = get_timer_state(company=company, employee=employee)
    if request.method != "POST":
        return redirect("timetracking:entry_list")

    if not timer_state.is_running or not timer_state.started_at:
        messages.info(request, "Timer is not running.")
        return redirect("timetracking:entry_list")

    now = timezone.now()
    total_seconds = _timer_total_seconds(timer_state, now)
    minutes = max(0, int(total_seconds // 60))

    # For record-keeping, if paused we treat ended_at as paused_at; else now.
    ended = timer_state.paused_at or now
    started = ended - timedelta(seconds=total_seconds)

    with transaction.atomic():
        entry = TimeEntry.objects.create(
            company=company,
            employee=employee,
            client=timer_state.client,
            project=timer_state.project,
            started_at=started,
            ended_at=ended,
            duration_minutes=minutes,
            billable=True,
            note=timer_state.note or "",
            status=TimeStatus.DRAFT,
            updated_by_user=request.user,
        )

        # If a service was selected/entered, attach it as a single service row consuming full duration.
        svc_name = ""
        svc_item = timer_state.service_catalog_item
        if svc_item:
            svc_name = svc_item.name
        elif (timer_state.service_name or "").strip():
            svc_name = (timer_state.service_name or "").strip()

        if svc_name and minutes > 0:
            TimeEntryService.objects.create(
                time_entry=entry,
                catalog_item=svc_item,
                name=svc_name,
                minutes=minutes,
                updated_by_user=request.user,
            )

        # reset timer running state (keep last selections for convenience)
        timer_state.is_running = False
        timer_state.is_paused = False
        timer_state.paused_at = None
        timer_state.elapsed_seconds = 0
        timer_state.started_at = None
        # NOTE: We intentionally keep project/service/note so the next start is faster.
        # Client will remain aligned to project via model clean/save.
        timer_state.updated_by_user = request.user
        timer_state.save()

        # Persist last selections.
        persist_timer_defaults(company=company, employee=employee, timer_state=timer_state)

    log_event(
        company=company,
        actor=employee,
        event_type="timer.stopped",
        object_type="TimeEntry",
        object_id=entry.id,
        summary="Stopped timer (created time entry)",
        payload={"duration_minutes": minutes},
        request=request,
    )

    messages.success(request, f"Timer stopped. Created time entry ({minutes} min).")
    return redirect("timetracking:entry_detail", pk=entry.pk)


@company_context_required
def timer_clear(request):
    company = request.active_company
    employee = request.active_employee

    timer_state = get_timer_state(company=company, employee=employee)
    if request.method != "POST":
        return redirect("timetracking:timer_panel")

    if timer_state.is_running:
        messages.error(request, "Stop the timer before clearing selections.")
        return redirect("timetracking:timer_panel")

    timer_state.project = None
    timer_state.client = None
    timer_state.service_catalog_item = None
    timer_state.service_name = ""
    timer_state.note = ""
    timer_state.updated_by_user = request.user
    timer_state.save()

    clear_timer_defaults(company=company, employee=employee)

    messages.success(request, "Timer selections cleared.")
    return redirect("timetracking:timer_panel")
