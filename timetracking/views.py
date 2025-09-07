# timetracking/views.py
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from company.utils import get_active_company, require_company_admin
from core.decorators import require_subscription
from core.models import Notification
from company.services import notify_company
from core.utils import combine_midday, week_range
from projects.models import Project

from .models import TimeEntry
from .forms import TimeEntryForm, TimesheetSubmitForm, TimesheetWeekForm


# --- helpers -----------------------------------------------------------------


def _running_entry(user, company):
    return (
        TimeEntry.objects.filter(user=user, company=company, end_time__isnull=True)
        .select_related("project")
        .order_by("-start_time")
        .first()
    )


# --- topbar dropdown partial (server-rendered) --------------------------------


@login_required
def time_dropdown(request):
    company = get_active_company(request)
    active = TimeEntry.active_for(request.user, company=company)
    form = TimeEntryForm(user=request.user, instance=active)
    recent = (
        TimeEntry.objects.filter(user=request.user, company=company)
        .select_related("project")
        .order_by("-start_time")[:6]
    )
    return render(
        request,
        "core/_time_dropdown.html",
        {"active_entry": active, "form": form, "recent_entries": recent},
    )


# --- timer API used by timer.js ----------------------------------------------


@login_required
def timer_status(request):
    company = get_active_company(request)
    if not company:
        return JsonResponse({"running": False, "error": "No active company."}, status=400)
    te = _running_entry(request.user, company)
    if not te:
        return JsonResponse({"running": False})
    elapsed = int((timezone.now() - te.start_time).total_seconds())
    return JsonResponse(
        {
            "running": True,
            "entry_id": str(te.id),
            "project_id": te.project_id,  # type: ignore
            "project_name": te.project.name,
            "start_time": te.start_time.isoformat(),
            "notes": te.notes or "",
            "elapsed_seconds": max(0, elapsed),
            "server_time": timezone.now().isoformat(),
        }
    )


@require_POST
@login_required
@transaction.atomic
def timer_start(request):
    company = get_active_company(request)
    if not company:
        return JsonResponse({"ok": False, "error": "No active company."}, status=400)

    pid_raw = (request.POST.get("project_id") or "").strip()
    try:
        pid = int(pid_raw)
    except ValueError:
        return JsonResponse({"ok": False, "error": "Select a valid project."}, status=400)

    project = get_object_or_404(Project, pk=pid, company=company)

    # Stop any running timer first (never two running)
    running = _running_entry(request.user, company)
    if running:
        running.end_time = timezone.now()
        running.save(update_fields=["end_time", "hours"])

    te = TimeEntry.objects.create(
        project=project,
        user=request.user,
        company=company,
        start_time=timezone.now(),
        notes=(request.POST.get("notes") or "").strip(),
        is_billable=True,
    )
    return JsonResponse({"ok": True, "entry_id": str(te.id)})


@require_POST
@login_required
@transaction.atomic
def timer_stop(request):
    company = get_active_company(request)
    if not company:
        return JsonResponse({"ok": False, "error": "No active company."}, status=400)

    te = _running_entry(request.user, company)
    if not te:
        return JsonResponse({"ok": False, "error": "No active timer."}, status=400)

    # Optional: save notes on stop
    notes = (request.POST.get("notes") or "").strip()
    if notes:
        te.notes = notes

    te.end_time = timezone.now()
    te.save(update_fields=["end_time", "hours", "notes"])
    return JsonResponse({"ok": True, "hours": float(te.hours or 0)})


@require_POST
@login_required
def timer_save(request):
    company = get_active_company(request)
    if not company:
        return JsonResponse({"ok": False, "error": "No active company."}, status=400)

    eid = (request.POST.get("entry_id") or "").strip()  # UUID string
    te = get_object_or_404(TimeEntry, pk=eid, user=request.user, company=company)
    te.notes = (request.POST.get("notes") or "").strip()
    te.save(update_fields=["notes"])
    return JsonResponse({"ok": True})


@require_POST
@login_required
@transaction.atomic
def timer_delete(request, pk):
    """Delete a time entry by UUID (string); disallow if already invoiced."""
    company = get_active_company(request)
    if not company:
        return JsonResponse({"ok": False, "error": "No active company."}, status=400)

    te = get_object_or_404(TimeEntry, pk=pk, user=request.user, company=company)
    if te.invoice_id:  # type: ignore
        return JsonResponse({"ok": False, "error": "Entry is already invoiced."}, status=400)
    te.delete()
    return JsonResponse({"ok": True})


# --- pages -------------------------------------------------------------------


@login_required
@require_subscription
def time_list(request):
    """Simple paginated list of the user's time entries."""
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company.")
        return redirect("dashboard:home")

    qs = (
        TimeEntry.objects.filter(user=request.user, company=company)
        .select_related("project")
        .order_by("-start_time", "-id")
    )

    # Optional quick search by project name or note text
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(project__name__icontains=q) | Q(notes__icontains=q))

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "timetracking/time_list.html", {"page_obj": page_obj, "q": q})


@login_required
@require_subscription
@transaction.atomic
def project_timer_start(request, pk: int):
    """Start a timer on a specific project; stop any existing running timer first."""
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company.")
        return redirect("dashboard:home")

    project = get_object_or_404(Project, pk=pk, company=company)

    running = (
        TimeEntry.objects.select_for_update()
        .filter(user=request.user, company=company, end_time__isnull=True)
        .order_by("-start_time")
        .first()
    )
    if running:
        running.end_time = timezone.now()
        running.save(update_fields=["end_time", "hours"])

    TimeEntry.objects.create(
        project=project,
        user=request.user,
        company=company,
        start_time=timezone.now(),
        notes="",
        is_billable=True,
    )

    messages.success(request, "Timer started.")
    return redirect("projects:project_detail", pk=pk)


@login_required
@require_subscription
@transaction.atomic
def project_timer_stop(request, pk: int):
    """Stop the running timer for this project (if any)."""
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company.")
        return redirect("dashboard:home")

    project = get_object_or_404(Project, pk=pk, company=company)

    entry = (
        TimeEntry.objects.select_for_update()
        .filter(project=project, user=request.user, company=company, end_time__isnull=True)
        .order_by("-start_time")
        .first()
    )
    if not entry:
        messages.warning(request, "No active timer.")
        return redirect("projects:project_detail", pk=pk)

    entry.end_time = timezone.now()
    entry.save(update_fields=["end_time", "hours"])

    try:
        hours_str = f"{Decimal(entry.hours):.2f}"
    except Exception:
        hours_str = str(entry.hours)
    messages.success(request, f"Timer stopped. Added {hours_str}h.")
    return redirect("projects:project_detail", pk=pk)


@login_required
@require_subscription
def timeentry_create(request, pk: int):
    """
    Manual add/edit page for a single time entry tied to a project.
    Normalizes naive datetimes to the user's (or site) timezone and
    computes hours if both timestamps are present but hours omitted.
    """
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company.")
        return redirect("dashboard:home")

    project = get_object_or_404(Project, pk=pk, company=company)

    if request.method == "POST":
        form = TimeEntryForm(request.POST, user=request.user)
        if form.is_valid():
            t: TimeEntry = form.save(commit=False)
            t.project = project
            t.user = request.user
            t.company = company

            # Make naive datetimes aware using user's preferred tz or SITE TIME_ZONE
            tzname = getattr(getattr(request.user, "profile", None), "timezone", "") or settings.TIME_ZONE
            tz = ZoneInfo(tzname)

            for field in ("start_time", "end_time"):
                dt = getattr(t, field, None)
                if dt and timezone.is_naive(dt):
                    setattr(t, field, timezone.make_aware(dt, tz))

            # If both provided but hours empty/zero, compute hours precisely
            if t.start_time and t.end_time and (t.hours is None or t.hours == Decimal("0.00")):
                seconds = (t.end_time - t.start_time).total_seconds()
                if seconds > 0:
                    hrs = Decimal(seconds) / Decimal("3600")
                    t.hours = hrs.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Guard negatives; normalize to 2 decimals if provided
            if t.hours is not None and t.hours < 0:
                messages.error(request, "Hours cannot be negative.")
                return render(request, "core/timeentry_form.html", {"form": form, "project": project})
            if t.hours is not None:
                t.hours = Decimal(t.hours).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            t.save()

            notify_company(
                company,
                request.user,
                f"Time entry added on {project.name}: {t.hours or 'timer'} h",
                url=reverse("projects:project_detail", args=[project.pk]),
                kind=Notification.TIME_ADDED,
            )
            messages.success(request, "Time entry added.")
            return redirect("projects:project_detail", pk=pk)
    else:
        form = TimeEntryForm(user=request.user)

    return render(request, "core/timeentry_form.html", {"form": form, "project": project})


# --- Timesheets & approvals ---------------------------------------------------


@login_required
@require_subscription
def timesheet_week(request):
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company.")
        return redirect("dashboard:home")

    today = timezone.now().date()
    default_week = today - timedelta(days=today.weekday())  # Monday

    if request.method == "POST":
        form = TimesheetWeekForm(request.POST, company=company, user=request.user)
        if form.is_valid():
            week = form.cleaned_data["week"]
            project = form.cleaned_data["project"]
            note = form.cleaned_data.get("note") or ""
            mon, sun = week_range(week)
            days = [mon + timedelta(days=i) for i in range(7)]
            values = [
                form.cleaned_data.get("mon"),
                form.cleaned_data.get("tue"),
                form.cleaned_data.get("wed"),
                form.cleaned_data.get("thu"),
                form.cleaned_data.get("fri"),
                form.cleaned_data.get("sat"),
                form.cleaned_data.get("sun"),
            ]

            created, updated = 0, 0
            for d, hours in zip(days, values):
                if hours and hours > 0:
                    te = (
                        TimeEntry.objects.filter(
                            project=project,
                            user=request.user,
                            invoice__isnull=True,
                            start_time__date=d,
                            notes__icontains="(Timesheet)",
                        )
                        .order_by("-id")
                        .first()
                    )
                    if te:
                        te.hours = hours
                        if not te.start_time:
                            te.start_time = combine_midday(d)
                        te.status = TimeEntry.DRAFT
                        te.notes = f"{note} (Timesheet)".strip()
                        te.save(update_fields=["hours", "start_time", "status", "notes"])
                        updated += 1
                    else:
                        TimeEntry.objects.create(
                            project=project,
                            user=request.user,
                            company=company,  # <- required
                            start_time=combine_midday(d),
                            hours=hours,
                            notes=f"{note} (Timesheet)".strip(),
                            is_billable=True,
                            status=TimeEntry.DRAFT,
                        )
                        created += 1

            messages.success(request, f"Timesheet saved. Created {created}, updated {updated}.")
            return redirect("timetracking:timesheet_week")
    else:
        form = TimesheetWeekForm(company=company, user=request.user, initial={"week": default_week})

    mon, sun = week_range(form.initial.get("week") or default_week)
    entries = (
        TimeEntry.objects.filter(
            project__company=company,
            user=request.user,
            start_time__date__gte=mon,
            start_time__date__lte=sun,
        )
        .select_related("project")
        .order_by("project__name", "start_time")
    )
    return render(
        request,
        "timetracking/timesheet_week.html",
        {"form": form, "entries": entries, "week_start": mon, "week_end": sun},
    )


@require_POST
@login_required
@require_subscription
def timesheet_submit_week(request):
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company.")
        return redirect("dashboard:home")

    form = TimesheetSubmitForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid week.")
        return redirect("timetracking:timesheet_week")

    week = form.cleaned_data["week"]
    mon, sun = week_range(week)
    qs = TimeEntry.objects.filter(
        project__company=company,
        user=request.user,
        invoice__isnull=True,
        start_time__date__gte=mon,
        start_time__date__lte=sun,
        status__in=[TimeEntry.DRAFT, TimeEntry.REJECTED],
    )
    now = timezone.now()
    updated = qs.update(status=TimeEntry.SUBMITTED, submitted_at=now)
    messages.success(request, f"Submitted {updated} entries for approval ({mon}–{sun}).")
    return redirect("timetracking:timesheet_week")


@login_required
@require_subscription
def approvals_list(request):
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company.")
        return redirect("dashboard:home")

    if not require_company_admin(request.user, company):
        messages.error(request, "You don't have permission to approve time.")
        return redirect("dashboard:home")

    pending = (
        TimeEntry.objects.filter(project__company=company, status=TimeEntry.SUBMITTED)
        .select_related("user", "project")
        .order_by("user__email", "start_time")
    )

    groups: dict[tuple[int, date], dict] = {}
    for t in pending:
        wk, _ = week_range(t.start_time.date())
        key = (t.user_id, wk)  # type: ignore
        groups.setdefault(key, {"user": t.user, "week": wk, "entries": []})
        groups[key]["entries"].append(t)

    return render(request, "timetracking/approvals_list.html", {"groups": groups})


@require_POST
@login_required
@require_subscription
def approvals_decide(request):
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company.")
        return redirect("dashboard:home")

    if not require_company_admin(request.user, company):
        messages.error(request, "You don't have permission to approve time.")
        return redirect("timetracking:approvals_list")

    action = request.POST.get("action")
    user_id = request.POST.get("user_id")
    week_str = request.POST.get("week")  # YYYY-MM-DD (monday)
    reason = (request.POST.get("reason") or "").strip()

    try:
        wk = date.fromisoformat(week_str)
    except Exception:
        messages.error(request, "Invalid week date.")
        return redirect("timetracking:approvals_list")

    mon, sun = week_range(wk)
    qs = TimeEntry.objects.filter(
        project__company=company,
        user_id=user_id,
        status=TimeEntry.SUBMITTED,
        start_time__date__gte=mon,
        start_time__date__lte=sun,
    )

    now = timezone.now()
    if action == "approve":
        updated = qs.update(
            status=TimeEntry.APPROVED, approved_at=now, approved_by_id=request.user.id
        )
        messages.success(request, f"Approved {updated} entries for week starting {wk}.")
    elif action == "reject":
        updated = qs.update(status=TimeEntry.REJECTED, reject_reason=reason)
        messages.success(request, f"Rejected {updated} entries for week starting {wk}.")
    else:
        messages.error(request, "Unknown action.")
    return redirect("timetracking:approvals_list")
