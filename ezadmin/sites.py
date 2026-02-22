from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.db import models
from django.http import HttpRequest
from django.urls import reverse
from django.utils.text import capfirst

from companies.models import Company

from .mixins import (
    CUSTOMERS_ADMIN_COMPANY_SESSION_KEY,
    CustomersScopedAdminMixin,
    get_selected_company_id,
    model_has_company_fk,
)


@dataclass(frozen=True)
class AdminSection:
    key: str
    title: str
    app_labels: tuple[str, ...]


OPS_SECTIONS: tuple[AdminSection, ...] = (
    AdminSection(
        key="platform",
        title="Platform Configuration",
        app_labels=("ops", "core", "billing"),
    ),
    AdminSection(
        key="security",
        title="Security & Accounts",
        app_labels=("accounts", "audit"),
    ),
    AdminSection(
        key="integrations",
        title="Integrations",
        app_labels=("integrations",),
    ),
)


# Tight whitelist of what belongs in the *platform* admin.
# Customer data is accessed via the Customers Admin (tenant-scoped) instead.
OPS_ALLOWED_APP_LABELS: tuple[str, ...] = (
    "ops",
    "core",
    "billing",
    "accounts",
    "audit",
    "integrations",
)


CUSTOMER_SECTIONS: tuple[AdminSection, ...] = (
    AdminSection(
        key="company",
        title="Company",
        app_labels=("companies",),
    ),
    AdminSection(
        key="crm",
        title="CRM",
        app_labels=("crm",),
    ),
    AdminSection(
        key="work",
        title="Projects & Time",
        app_labels=("projects", "timetracking"),
    ),
    AdminSection(
        key="documents",
        title="Documents",
        app_labels=("documents",),
    ),
    AdminSection(
        key="money",
        title="Payments & Expenses",
        app_labels=("payments", "expenses", "payables", "accounting"),
    ),
    AdminSection(
        key="notes",
        title="Notes",
        app_labels=("notes",),
    ),
)


def _build_customer_quick_links(site_name: str) -> list[dict[str, str]]:
    """Best-effort quick links for the Customers Admin.

    We keep this defensive: if a model isn't registered or a URL name changes,
    we simply omit that link.
    """

    candidates: list[tuple[str, str, str]] = [
        ("Clients", "crm", "client"),
        ("Projects", "projects", "project"),
        ("Time Entries", "timetracking", "timeentry"),
        ("Documents", "documents", "document"),
        ("Payments", "payments", "payment"),
        ("Expenses", "expenses", "expense"),
        ("Vendors", "payables", "vendor"),
    ]

    links: list[dict[str, str]] = []
    for label, app_label, model_name in candidates:
        try:
            url = reverse(f"{site_name}:{app_label}_{model_name}_changelist")
        except Exception:
            continue
        links.append({"label": label, "url": url})
    return links


def _section_for_app(app_label: str, sections: Iterable[AdminSection]) -> str:
    for s in sections:
        if app_label in s.app_labels:
            return s.key
    return "other"


class EZBaseAdminSite(AdminSite):
    site_header = "EZ360PM"
    site_title = "EZ360PM Admin"
    index_title = "Control Panel"

    # Use our templates to support sections
    index_template = "admin/ez360_index.html"

    def each_context(self, request: HttpRequest):
        ctx = super().each_context(request)
        ctx["ez360_site_name"] = "EZ360PM"
        # Used by our admin/base_site.html override so the header links to the
        # correct AdminSite index.
        try:
            ctx["ezadmin_index_url"] = reverse(f"{self.name}:index")
        except Exception:
            pass
        return ctx


class OpsAdminSite(EZBaseAdminSite):
    site_header = "EZ360PM — Settings"
    site_title = "EZ360PM Settings"
    index_title = "EZ360PM Settings"

    def get_app_list(self, request: HttpRequest, app_label=None):
        app_list = super().get_app_list(request, app_label)

        # Tag each app with a section key for the index template
        for app in app_list:
            app["section"] = _section_for_app(app["app_label"], OPS_SECTIONS)

        # Sort by section order then app name
        section_order = {s.key: i for i, s in enumerate(OPS_SECTIONS)}
        section_order["other"] = 999

        app_list.sort(key=lambda a: (section_order.get(a.get("section", "other"), 999), a.get("name", "")))
        return app_list

    def each_context(self, request: HttpRequest):
        ctx = super().each_context(request)
        ctx["ezadmin_sections"] = OPS_SECTIONS
        ctx["ezadmin_mode"] = "ops"
        return ctx

    def has_permission(self, request: HttpRequest) -> bool:
        """Platform admin is intentionally restricted.

        For v1: superusers only. This is safer than "is_staff" given the
        operational blast radius of platform configuration.
        """

        user = getattr(request, "user", None)
        if not user or not user.is_active:
            return False
        return bool(user.is_superuser)


class CustomersAdminSite(EZBaseAdminSite):
    site_header = "EZ360PM — Customers"
    site_title = "EZ360PM Customers"
    index_title = "EZ360PM Customers"

    def each_context(self, request: HttpRequest):
        ctx = super().each_context(request)

        selected_company_id = get_selected_company_id(request)
        request.ezadmin_selected_company_id = selected_company_id

        ctx["ezadmin_mode"] = "customers"
        ctx["ezadmin_sections"] = CUSTOMER_SECTIONS

        # Limit selectable companies for non-superusers to companies where the user
        # has an active EmployeeProfile.
        companies_qs = Company.objects.filter(is_active=True)
        if not request.user.is_superuser:
            companies_qs = companies_qs.filter(employees__user=request.user, employees__is_active=True).distinct()
        ctx["ezadmin_companies"] = companies_qs.order_by("name")

        ctx["ezadmin_selected_company_id"] = selected_company_id
        ctx["ezadmin_switch_company_url"] = reverse("customers_admin:switch_company")

        # If a selected company is no longer allowed/available, clear it.
        if selected_company_id and not ctx["ezadmin_companies"].filter(id=selected_company_id).exists():
            request.session.pop(CUSTOMERS_ADMIN_COMPANY_SESSION_KEY, None)
            selected_company_id = None
            request.ezadmin_selected_company_id = None
            ctx["ezadmin_selected_company_id"] = None

        # Selected company object (for the index dashboard).
        selected_company = None
        if selected_company_id:
            selected_company = ctx["ezadmin_companies"].filter(id=selected_company_id).first()
        ctx["ezadmin_selected_company"] = selected_company

        # Quick links (shown on the Customers Admin index when a company is selected)
        ctx["ezadmin_quick_links"] = _build_customer_quick_links(site_name=self.name)
        return ctx

    def has_permission(self, request: HttpRequest) -> bool:
        """Customers admin is for staff.

        Non-superusers can only use it for companies where they have an active
        EmployeeProfile (enforced via company filtering + queryset scoping).
        """

        user = getattr(request, "user", None)
        if not user or not user.is_active:
            return False
        return bool(user.is_staff)

    def get_app_list(self, request: HttpRequest, app_label=None):
        app_list = super().get_app_list(request, app_label)

        for app in app_list:
            app["section"] = _section_for_app(app["app_label"], CUSTOMER_SECTIONS)

        section_order = {s.key: i for i, s in enumerate(CUSTOMER_SECTIONS)}
        section_order["other"] = 999
        app_list.sort(key=lambda a: (section_order.get(a.get("section", "other"), 999), a.get("name", "")))
        return app_list

    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()

        def switch_company_view(request: HttpRequest):
            """Persist selected company in session and redirect back."""
            if not request.user.is_active or not request.user.is_staff:
                # AdminSite.admin_view would normally handle this, but be explicit.
                from django.http import HttpResponseForbidden

                return HttpResponseForbidden("Forbidden")

            company_id = (request.POST.get("company_id") or request.GET.get("company_id") or "").strip()
            if company_id:
                request.session[CUSTOMERS_ADMIN_COMPANY_SESSION_KEY] = company_id
            else:
                request.session.pop(CUSTOMERS_ADMIN_COMPANY_SESSION_KEY, None)

            next_url = request.POST.get("next") or request.GET.get("next")
            if not next_url:
                next_url = reverse("customers_admin:index")

            from django.shortcuts import redirect

            return redirect(next_url)

        custom = [
            path(
                "switch-company/",
                self.admin_view(switch_company_view),
                name="switch_company",
            )
        ]
        return custom + urls


ops_admin_site = OpsAdminSite(name="ops_admin")
customers_admin_site = CustomersAdminSite(name="customers_admin")


class CustomerCompanyAdmin(admin.ModelAdmin):
    """Company listing inside the customer-scoped admin.

    We keep it read-only-ish; company selection should happen via the switcher.
    """

    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


def register_from_default_admin():
    """Clone registrations from Django's default admin.site into our two sites.

    This avoids having to touch every app's admin.py immediately.
    We can iterate later to tighten what appears where.
    """

    default_registry = getattr(admin.site, "_registry", {})

    for model, model_admin in default_registry.items():
        app_label = getattr(model._meta, "app_label", "")

        # 1) Ops site: register only platform models
        if app_label in OPS_ALLOWED_APP_LABELS:
            try:
                ops_admin_site.register(model, model_admin.__class__)
            except admin.sites.AlreadyRegistered:
                pass

        # 2) Customers site: register only company-scoped models + Company itself
        if model is Company:
            try:
                customers_admin_site.register(model, CustomerCompanyAdmin)
            except admin.sites.AlreadyRegistered:
                pass
            continue

        if not model_has_company_fk(model):
            continue

        # Wrap the existing ModelAdmin to enforce company scoping
        wrapped_admin = type(
            f"CustomersScoped{model_admin.__class__.__name__}",
            (CustomersScopedAdminMixin, model_admin.__class__),
            {},
        )
        try:
            customers_admin_site.register(model, wrapped_admin)
        except admin.sites.AlreadyRegistered:
            pass
