from __future__ import annotations

from django.contrib import admin
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.http import HttpRequest


CUSTOMERS_ADMIN_COMPANY_SESSION_KEY = "ezadmin_customers_company_id"


def model_has_company_fk(model: type[models.Model]) -> bool:
    """Return True if the model has a FK named 'company'."""
    try:
        field = model._meta.get_field("company")
    except FieldDoesNotExist:
        return False
    return isinstance(field, models.ForeignKey)


def get_selected_company_id(request: HttpRequest) -> str | None:
    raw = request.session.get(CUSTOMERS_ADMIN_COMPANY_SESSION_KEY)
    if not raw:
        return None
    return str(raw)


class CustomersScopedAdminMixin(admin.ModelAdmin):
    """A mixin that scopes admin queries and FK choices to the selected company.

    This is intentionally conservative:
    - If a model has no `company` FK, we don't filter (caller should usually not register the model)
    - If no company is selected, queryset is empty (prevents cross-tenant browsing by accident)
    """

    def get_queryset(self, request: HttpRequest):
        qs = super().get_queryset(request)
        if not model_has_company_fk(self.model):
            return qs

        company_id = getattr(request, "ezadmin_selected_company_id", None)
        if not company_id:
            return qs.none()
        return qs.filter(company_id=company_id)

    def formfield_for_foreignkey(self, db_field, request: HttpRequest, **kwargs):
        """Limit FK dropdowns to the selected company when possible."""
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        company_id = getattr(request, "ezadmin_selected_company_id", None)
        if not company_id:
            return formfield

        rel_model = getattr(db_field.remote_field, "model", None)
        if rel_model is not None and model_has_company_fk(rel_model):
            try:
                formfield.queryset = formfield.queryset.filter(company_id=company_id)
            except Exception:
                # Defensive: don't break the admin if a queryset can't be filtered
                pass
        return formfield
