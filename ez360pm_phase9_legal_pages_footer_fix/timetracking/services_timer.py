from __future__ import annotations

from django.db import transaction

from companies.models import Company, EmployeeProfile

from .models import TimerState, TimeTrackingSettings


def _get_or_create_time_settings(company: Company, employee: EmployeeProfile) -> TimeTrackingSettings:
    obj, _ = TimeTrackingSettings.objects.get_or_create(company=company, employee=employee)
    return obj


def get_timer_state(company: Company, employee: EmployeeProfile) -> TimerState:
    """Get or create TimerState and initialize selections from per-employee defaults.

    TimerState is a OneToOne row and may be deleted/recreated (sync resets, data repair, etc.).
    Corporate UX expects "remember my last timer selection" to survive recreation.
    """
    with transaction.atomic():
        timer_state, created = TimerState.objects.select_for_update().get_or_create(company=company, employee=employee)
        settings = _get_or_create_time_settings(company, employee)

        has_any_selection = bool(
            timer_state.project_id
            or timer_state.service_catalog_item_id
            or (timer_state.service_name or "").strip()
            or (timer_state.note or "").strip()
        )

        if created or not has_any_selection:
            if settings.last_project_id:
                timer_state.project_id = settings.last_project_id
            if settings.last_service_catalog_item_id:
                timer_state.service_catalog_item_id = settings.last_service_catalog_item_id
            if (settings.last_service_name or "").strip():
                timer_state.service_name = settings.last_service_name
            if (settings.last_note or "").strip():
                timer_state.note = settings.last_note
            timer_state.save()

        return timer_state


def persist_timer_defaults(company: Company, employee: EmployeeProfile, timer_state: TimerState) -> None:
    """Persist current TimerState selections to the employee's TimeTrackingSettings."""
    settings = _get_or_create_time_settings(company, employee)
    settings.last_project_id = timer_state.project_id
    settings.last_service_catalog_item_id = timer_state.service_catalog_item_id
    settings.last_service_name = timer_state.service_name or ""
    settings.last_note = timer_state.note or ""
    settings.save(
        update_fields=[
            "last_project",
            "last_service_catalog_item",
            "last_service_name",
            "last_note",
            "updated_at",
        ]
    )


def clear_timer_defaults(company: Company, employee: EmployeeProfile) -> None:
    """Clear persisted timer defaults."""
    settings = _get_or_create_time_settings(company, employee)
    settings.last_project = None
    settings.last_service_catalog_item = None
    settings.last_service_name = ""
    settings.last_note = ""
    settings.save(
        update_fields=[
            "last_project",
            "last_service_catalog_item",
            "last_service_name",
            "last_note",
            "updated_at",
        ]
    )
