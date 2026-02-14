from __future__ import annotations

import csv
from datetime import datetime
from typing import Optional

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from companies.decorators import require_min_role
from companies.models import EmployeeRole

from .models import AuditEvent


def _parse_date(value: str) -> Optional[datetime]:
    """Parse YYYY-MM-DD into an aware datetime at local midnight."""
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return None
    # interpret as local date; convert to aware
    return timezone.make_aware(datetime(dt.year, dt.month, dt.day, 0, 0, 0))


@require_min_role(EmployeeRole.MANAGER)
def audit_event_list(request: HttpRequest) -> HttpResponse:
    company = request.active_company

    qs = AuditEvent.objects.filter(company=company).select_related("actor").order_by("-created_at")

    q = (request.GET.get("q") or "").strip()
    event_type = (request.GET.get("event_type") or "").strip()
    object_type = (request.GET.get("object_type") or "").strip()
    actor = (request.GET.get("actor") or "").strip()
    date_from = (request.GET.get("from") or "").strip()
    date_to = (request.GET.get("to") or "").strip()

    if q:
        qs = qs.filter(
            Q(event_type__icontains=q)
            | Q(object_type__icontains=q)
            | Q(summary__icontains=q)
            | Q(actor__username_public__icontains=q)
        )
    if event_type:
        qs = qs.filter(event_type__icontains=event_type)
    if object_type:
        qs = qs.filter(object_type__icontains=object_type)
    if actor:
        qs = qs.filter(Q(actor__username_public__icontains=actor) | Q(actor__display_name__icontains=actor))

    dt_from = _parse_date(date_from) if date_from else None
    if dt_from:
        qs = qs.filter(created_at__gte=dt_from)

    dt_to = _parse_date(date_to) if date_to else None
    if dt_to:
        # inclusive end date: add 1 day midnight
        qs = qs.filter(created_at__lt=dt_to + timezone.timedelta(days=1))

    paginator = Paginator(qs, 50)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    ctx = {
        "page_obj": page_obj,
        "q": q,
        "event_type": event_type,
        "object_type": object_type,
        "actor": actor,
        "date_from": date_from,
        "date_to": date_to,
    }
    return render(request, "audit/event_list.html", ctx)


@require_min_role(EmployeeRole.MANAGER)
def audit_event_detail(request: HttpRequest, pk) -> HttpResponse:
    company = request.active_company
    event = get_object_or_404(AuditEvent.objects.select_related("actor"), company=company, pk=pk)
    return render(request, "audit/event_detail.html", {"event": event})


@require_min_role(EmployeeRole.MANAGER)
def audit_event_export_csv(request: HttpRequest) -> HttpResponse:
    company = request.active_company

    qs = AuditEvent.objects.filter(company=company).select_related("actor").order_by("-created_at")
    # reuse same filters as list
    q = (request.GET.get("q") or "").strip()
    event_type = (request.GET.get("event_type") or "").strip()
    object_type = (request.GET.get("object_type") or "").strip()
    actor = (request.GET.get("actor") or "").strip()
    date_from = (request.GET.get("from") or "").strip()
    date_to = (request.GET.get("to") or "").strip()

    if q:
        qs = qs.filter(
            Q(event_type__icontains=q)
            | Q(object_type__icontains=q)
            | Q(summary__icontains=q)
            | Q(actor__username_public__icontains=q)
        )
    if event_type:
        qs = qs.filter(event_type__icontains=event_type)
    if object_type:
        qs = qs.filter(object_type__icontains=object_type)
    if actor:
        qs = qs.filter(Q(actor__username_public__icontains=actor) | Q(actor__display_name__icontains=actor))

    dt_from = _parse_date(date_from) if date_from else None
    if dt_from:
        qs = qs.filter(created_at__gte=dt_from)

    dt_to = _parse_date(date_to) if date_to else None
    if dt_to:
        qs = qs.filter(created_at__lt=dt_to + timezone.timedelta(days=1))

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="audit_{company.id}_events.csv"'

    writer = csv.writer(response)
    writer.writerow(["created_at", "event_type", "object_type", "object_id", "actor", "summary", "ip_address"])
    for ev in qs[:5000]:
        actor_label = ""
        if ev.actor_id:
            actor_label = ev.actor.display_name or ev.actor.username_public
        writer.writerow([
            ev.created_at.isoformat(),
            ev.event_type,
            ev.object_type,
            str(ev.object_id or ""),
            actor_label,
            ev.summary,
            ev.ip_address or "",
        ])
    return response
