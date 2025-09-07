# estimates/views.py
from __future__ import annotations

# --- Third-party / Django ---
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.core.mail import EmailMessage

# --- Local apps ---
from company.services import notify_company
from company.utils import get_active_company
from core.forms import SendEmailForm
from core.views import _render_pdf_from_html
from projects.models import Project
from .models import Estimate, EstimateItem
from invoices.services import recalc_invoice

from core.decorators import require_subscription
from .forms import (
    ConvertEstimateToProjectForm,
    EstimateForm,
    EstimateItemFormSet,
)
from core.models import Notification
from .services import (
    convert_estimate_to_invoice,
    recalc_estimate,
)
from .utils import generate_estimate_number

# 🔧 If your project has different locations for these, adjust imports accordingly:
from invoices.utils import generate_invoice_number  # noqa: F401
from projects.utils import generate_project_number  # noqa: F401

# --- Plan helpers (features & limits) ---
try:
    from billing.utils import (  # type: ignore
        enforce_limit_or_upsell,  # type: ignore
        require_feature,          # type: ignore
    )
except Exception:
    def enforce_limit_or_upsell(company, key: str, current_count: int):
        return True, None
    def require_feature(key: str):
        def _deco(fn): return fn
        return _deco
    def require_tier_at_least(slug: str):
        def _deco(fn): return fn
        return _deco

User = get_user_model()
try:
    _require_estimates = require_feature("estimates")  # type: ignore
except Exception:
    def _require_estimates(fn):
        return fn


@login_required
@_require_estimates
def estimates_list(request):
    company = get_active_company(request)
    q = (request.GET.get("q") or "").strip()
    show_templates = request.GET.get("templates") == "1"

    qs = Estimate.objects.filter(company=company)
    if not show_templates:
        qs = qs.filter(is_template=False)

    if q:
        qs = qs.filter(
            Q(number__icontains=q)
            | Q(client__org__icontains=q)
            | Q(client__first_name__icontains=q)
            | Q(client__last_name__icontains=q)
            | Q(project__name__icontains=q)
        )

    qs = qs.select_related("client", "project").order_by("-issue_date", "-id")
    return render(
        request,
        "estimates/estimates_list.html",
        {"estimates": qs, "q": q, "show_templates": show_templates},
    )


@login_required
@require_subscription
@_require_estimates
def estimate_create(request):
    company = get_active_company(request)

    count = Estimate.objects.filter(company=company, is_template=False).count()
    ok, limit = enforce_limit_or_upsell(company, "max_estimates", count)
    if not ok:
        messages.warning(
            request,
            f"You've reached your plan’s limit of {limit} estimates. Upgrade to add more.",
        )
        return redirect("billing:plans")

    if request.method == "POST":
        form = EstimateForm(request.POST, company=company)
        formset = EstimateItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            est = form.save(commit=False)
            est.company = company
            if not est.number:
                est.number = generate_estimate_number(company)  # type: ignore
            est.save()
            notify_company(
                company,
                request.user,
                f"Estimate {est.number} created for {est.client}",
                url=reverse("estimates:estimate_detail", args=[est.pk]),
                kind=Notification.ESTIMATE_CREATED,
            )
            formset.instance = est
            formset.save()
            recalc_estimate(est)
            messages.success(request, "Estimate created.")
            return redirect("estimates:estimate_detail", pk=est.pk)
    else:
        form = EstimateForm(
            company=company, initial={"number": generate_estimate_number(company)}  # type: ignore
        )
        formset = EstimateItemFormSet()
    return render(
        request,
        "estimates/estimate_form.html",
        {"form": form, "formset": formset, "mode": "create"},
    )


@login_required
@require_subscription
@_require_estimates
def estimate_create_from(request, pk: int):
    company = get_active_company(request)
    tmpl = get_object_or_404(
        Estimate.objects.select_related("client", "project").prefetch_related("items"),
        pk=pk, company=company, is_template=True
    )

    count = Estimate.objects.filter(company=company, is_template=False).count()
    ok, limit = enforce_limit_or_upsell(company, "max_estimates", count)
    if not ok:
        messages.warning(
            request,
            f"You've reached your plan’s limit of {limit} estimates. Upgrade to add more.",
        )
        return redirect("billing:plans")

    if request.method == "POST":
        form = EstimateForm(request.POST, company=company)
        formset = EstimateItemFormSet(request.POST, prefix="items")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():  # type: ignore
                est = form.save(commit=False)
                est.company = company
                est.is_template = False
                est.status = Estimate.DRAFT
                if not est.number:
                    est.number = generate_estimate_number(company)  # type: ignore
                est.save()

                formset.instance = est
                formset.save()

                recalc_estimate(est)
            messages.success(request, "Estimate created from template.")
            return redirect("estimates:estimate_detail", pk=est.pk)
    else:
        form = EstimateForm(
            instance=None,
            company=company,
            initial={
                "client": tmpl.client_id,  # type: ignore
                "project": tmpl.project_id,  # type: ignore
                "number": generate_estimate_number(company),  # type: ignore
                "status": Estimate.DRAFT,
                "issue_date": timezone.now().date(),
                "valid_until": tmpl.valid_until,
                "tax": tmpl.tax,
                "notes": tmpl.notes,
                "is_template": False,
            },
        )
        initial_items = [
            {"description": it.description, "qty": it.qty, "unit_price": it.unit_price}
            for it in tmpl.items.all()  # type: ignore
        ]
        formset = EstimateItemFormSet(
            prefix="items",
            instance=Estimate(),
            queryset=EstimateItem.objects.none(),
            initial=initial_items,
        )

    return render(
        request,
        "estimates/estimate_form.html",
        {"form": form, "formset": formset, "mode": "create_from", "src": tmpl},
    )


@login_required
@require_subscription
@_require_estimates
def estimate_detail(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(
        Estimate.objects.select_related("client", "project"), pk=pk, company=company
    )
    recalc_estimate(est)
    return render(request, "estimates/estimate_detail.html", {"est": est})


@login_required
@require_subscription
@_require_estimates
def estimate_update(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(Estimate, pk=pk, company=company)
    if request.method == "POST":
        form = EstimateForm(request.POST, instance=est, company=company)
        formset = EstimateItemFormSet(request.POST, instance=est)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            recalc_estimate(est)
            messages.success(request, "Estimate updated.")
            return redirect("estimates:estimate_detail", pk=est.pk)
    else:
        form = EstimateForm(instance=est, company=company)
        formset = EstimateItemFormSet(instance=est)
    return render(
        request,
        "estimates/estimate_form.html",
        {"form": form, "formset": formset, "mode": "edit", "est": est},
    )


@login_required
@require_subscription
@_require_estimates
@require_http_methods(["POST"])
def estimate_delete(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(Estimate, pk=pk, company=company)
    est.delete()
    messages.success(request, "Estimate deleted.")
    return redirect("estimates:estimates_list")


@login_required
@require_subscription
@_require_estimates
@require_http_methods(["POST"])
def estimate_mark_sent(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(Estimate, pk=pk, company=company)
    est.status = Estimate.SENT
    est.last_sent_at = timezone.now()
    est.save(update_fields=["status", "last_sent_at"])
    messages.success(request, "Estimate marked as sent.")
    return redirect("estimates:estimate_detail", pk=pk)


@login_required
@require_subscription
@_require_estimates
@require_http_methods(["POST"])
def estimate_accept(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(Estimate, pk=pk, company=company)

    est.status = Estimate.ACCEPTED
    est.accepted_at = timezone.now()
    # Best-effort actor name
    actor = getattr(request.user, "get_full_name", lambda: "")() or getattr(request.user, "email", "") or "user"
    est.accepted_by = actor[:120]
    est.save(update_fields=["status", "accepted_at", "accepted_by"])

    notify_company(
        company,
        request.user,
        f"Estimate {est.number} accepted",
        url=reverse("estimates:estimate_detail", args=[est.pk]),
        kind=Notification.ESTIMATE_ACCEPTED,
    )
    messages.success(request, "Estimate accepted.")
    return redirect("estimates:estimate_detail", pk=pk)


@login_required
@require_subscription
@_require_estimates
@require_http_methods(["POST"])
def estimate_decline(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(Estimate, pk=pk, company=company)

    est.status = Estimate.DECLINED
    est.declined_at = timezone.now()
    actor = getattr(request.user, "get_full_name", lambda: "")() or getattr(request.user, "email", "") or "user"
    est.declined_by = actor[:120]
    est.save(update_fields=["status", "declined_at", "declined_by"])

    messages.success(request, "Estimate declined.")
    return redirect("estimates:estimate_detail", pk=pk)


@login_required
@require_subscription
@_require_estimates
def estimate_convert(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(
        Estimate.objects.select_related("client", "project"), pk=pk, company=company
    )
    inv = convert_estimate_to_invoice(est)
    if not inv.number:
        inv.number = generate_invoice_number(company)  # type: ignore
        inv.save(update_fields=["number"])
    notify_company(
        company,
        request.user,
        f"Estimate {est.number} converted to invoice {inv.number}",
        url=reverse("invoices:invoice_detail", args=[inv.pk]),
        kind=Notification.ESTIMATE_CONVERTED,
    )
    recalc_invoice(inv)
    messages.success(request, f"Converted to invoice {inv.number}.")
    return redirect("invoices:invoice_detail", pk=inv.pk)


# --- Public estimate views (no auth) ---

def _get_estimate_by_token(token):
    return get_object_or_404(
        Estimate.objects.select_related("client", "project"), public_token=token
    )


def estimate_public(request, token):
    est = _get_estimate_by_token(token)
    recalc_estimate(est)
    items = EstimateItem.objects.filter(estimate=est).order_by("id")
    can_act = est.status in (Estimate.DRAFT, Estimate.SENT)
    if est.valid_until and est.valid_until < timezone.localdate():
        can_act = False
    return render(
        request, "estimates/estimate_public.html", {"est": est, "items": items, "can_act": can_act}
    )


@require_http_methods(["POST"])
def estimate_public_accept(request, token):
    est = get_object_or_404(Estimate.objects.select_related("company"), public_token=token)
    # Block if already decided or expired
    if est.status in (Estimate.ACCEPTED, Estimate.DECLINED):
        return redirect("estimates:estimate_public", token=token)
    if est.valid_until and est.valid_until < timezone.localdate():
        messages.error(request, "This estimate is no longer valid.")
        return redirect("estimates:estimate_public", token=token)

    signer = (request.POST.get("name") or "").strip()
    note = (request.POST.get("note") or "").strip()

    est.status = Estimate.ACCEPTED
    est.accepted_at = timezone.now()
    est.accepted_by = (signer or "client")[:120]
    if note:
        est.client_note = (est.client_note + "\n" if est.client_note else "") + note
    est.save(update_fields=["status", "accepted_at", "accepted_by", "client_note"])

    try:
        notify_company(
            est.company,
            None,
            f"Estimate {est.number} accepted by {signer or 'client'}",
            url=reverse("estimates:estimate_detail", args=[est.pk]),
            kind=Notification.ESTIMATE_ACCEPTED,
            exclude_actor=False,
        )
    except Exception:
        pass

    messages.success(request, "Thanks! Your acceptance has been recorded.")
    return redirect("estimates:estimate_public", token=token)


@require_http_methods(["POST"])
def estimate_public_decline(request, token):
    est = get_object_or_404(Estimate.objects.select_related("company"), public_token=token)
    # Block if already decided or expired
    if est.status in (Estimate.ACCEPTED, Estimate.DECLINED):
        return redirect("estimates:estimate_public", token=token)
    if est.valid_until and est.valid_until < timezone.localdate():
        messages.error(request, "This estimate is no longer valid.")
        return redirect("estimates:estimate_public", token=token)

    signer = (request.POST.get("name") or "").strip()
    note = (request.POST.get("note") or "").strip()

    est.status = Estimate.DECLINED
    est.declined_at = timezone.now()
    est.declined_by = (signer or "client")[:120]
    if note:
        est.client_note = (est.client_note + "\n" if est.client_note else "") + note
    est.save(update_fields=["status", "declined_at", "declined_by", "client_note"])

    try:
        notify_company(
            est.company,
            None,
            f"Estimate {est.number} declined by {signer or 'client'}",
            url=reverse("estimates:estimate_detail", args=[est.pk]),
            kind=Notification.ESTIMATE_DECLINED, # type: ignore
            exclude_actor=False,
        )
    except Exception:
        pass

    messages.info(request, "Response recorded.")
    return redirect("estimates:estimate_public", token=token)


# =============================================================================
# Estimate -> Project
# =============================================================================

@login_required
@require_subscription
@_require_estimates
def estimate_convert_to_project(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(
        Estimate.objects.select_related("client", "project"), pk=pk, company=company
    )

    initial_mode = (
        ConvertEstimateToProjectForm.MODE_ATTACH
        if est.project_id  # type: ignore
        else ConvertEstimateToProjectForm.MODE_NEW  # type: ignore[attr-defined]
    )

    initial = {
        "mode": initial_mode,
        "new_name": (
            (getattr(est, "project", None) and est.project.name)  # type: ignore[union-attr]
        ) or f"{est.client or 'Client'} — {est.number}",
        "new_number": generate_project_number(company),  # type: ignore
    }

    form = ConvertEstimateToProjectForm(
        request.POST or None,
        company=company,
        client=getattr(est, "client", None),
        initial=initial,
    )

    if request.method == "POST" and form.is_valid():
        mode = form.cleaned_data["mode"]
        if mode == ConvertEstimateToProjectForm.MODE_ATTACH:
            proj = form.cleaned_data["existing_project"]
            if proj.company_id != company.id:  # type: ignore
                messages.error(request, "Project must belong to your company.")
                return redirect("estimates:estimate_detail", pk=pk)
        else:
            proj = Project.objects.create(
                company=company,
                client=est.client,
                number=form.cleaned_data.get("new_number")
                or generate_project_number(company),  # type: ignore
                name=form.cleaned_data.get("new_name") or f"Project from {est.number}",
                billing_type=form.cleaned_data.get("new_billing_type") or Project.HOURLY,
                estimated_hours=form.cleaned_data.get("new_estimated_hours") or 0,
                budget=form.cleaned_data.get("new_budget") or 0,
                start_date=form.cleaned_data.get("new_start_date"),
                due_date=form.cleaned_data.get("new_due_date"),
            )

        est.project = proj  # type: ignore
        if est.status != Estimate.ACCEPTED:
            est.status = Estimate.ACCEPTED
            est.accepted_at = est.accepted_at or timezone.now()
            est.accepted_by = est.accepted_by or (getattr(request.user, "email", "") or "system")[:120]
            est.save(update_fields=["project", "status", "accepted_at", "accepted_by"])
        else:
            est.save(update_fields=["project"])

        try:
            notify_company(
                company,
                request.user,
                f"Estimate {est.number} linked to project {proj.number} {proj.name}",
                url=reverse("projects:project_detail", args=[proj.pk]),
                kind=Notification.GENERIC,
            )
        except Exception:
            pass

        messages.success(
            request,
            f"Estimate {est.number} is now linked to project {proj.number} — {proj.name}.",
        )
        return redirect("projects:project_detail", pk=proj.pk)

    return render(request, "estimates/estimate_convert_project.html", {"est": est, "form": form})


# =============================================================================
# Email & PDF
# =============================================================================
@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def estimate_email(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(
        Estimate.objects.select_related("client", "project"), pk=pk, company=company
    )
    recalc_estimate(est)

    initial = {
        "to": getattr(est.client, "email", "") or "",
        "subject": f"Estimate {est.number} from {est.company.name}",
        "message": "",
    }

    form = SendEmailForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        to = [form.cleaned_data["to"]]
        cc_raw = form.cleaned_data.get("cc") or ""
        cc = [e.strip() for e in cc_raw.split(",") if e.strip()]
        subject = form.cleaned_data["subject"]
        body = form.cleaned_data["message"] or render_to_string(
            "core/email/estimate_email.txt", {"est": est, "site_url": settings.SITE_URL}
        )

        html = render_to_string("core/pdf/estimate.html", {"est": est})
        pdf_bytes = _render_pdf_from_html(html, base_url=request.build_absolute_uri("/"))
        filename = f"estimate_{est.number}.pdf"

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=to,
            cc=cc or None,
        )
        email.attach(filename, pdf_bytes, "application/pdf")
        email.send(fail_silently=False)

        # Mark as sent with timestamp
        est.status = Estimate.SENT
        est.last_sent_at = timezone.now()
        est.save(update_fields=["status", "last_sent_at"])

        messages.success(
            request,
            f"Estimate emailed to {to[0]}{(' (cc: ' + ', '.join(cc) + ')' if cc else '')}.",
        )
        return redirect("estimates:estimate_detail", pk=pk)

    return render(
        request,
        "core/email_send_form.html",
        {"form": form, "obj": est, "kind": "estimate"},
    )


@login_required
@require_subscription
def estimate_pdf(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(
        Estimate.objects.select_related("client", "project"), pk=pk, company=company
    )
    recalc_estimate(est)
    html = render_to_string("core/pdf/estimate.html", {"est": est})
    pdf_bytes = _render_pdf_from_html(html, base_url=request.build_absolute_uri("/"))
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="estimate_{est.number}.pdf"'
    return resp
