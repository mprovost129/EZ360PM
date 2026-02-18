from __future__ import annotations

from django.core.paginator import Paginator

from copy import deepcopy
from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Count
from django.db.models.functions import TruncDate
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from audit.services import log_event
from audit.models import AuditEvent
from companies.decorators import company_context_required, require_min_role
require_active_company = company_context_required
from companies.models import EmployeeRole
from projects.models import Project
from crm.models import Client
from documents.models import ClientStatementActivity
from documents.models import ClientStatementRecipientPreference
from timetracking.models import TimeEntry, TimeStatus

from decimal import Decimal

from .forms import DocumentForm, DocumentLineItemFormSet, DocumentWizardForm, NumberingSchemeForm, CreditNoteForm
from .models import (
    Document,
    DocumentLineItem,
    DocumentStatus,
    DocumentTemplate,
    DocumentType,
    NumberingScheme,
    CreditNote,
    CreditNoteStatus,
    CreditNoteNumberSequence,
    ClientCollectionsNote,
    CollectionsNoteStatus,
    StatementReminder,
    StatementReminderStatus,
)
from .services import allocate_document_number, ensure_numbering_scheme, recalc_document_totals
from .services_email import send_document_to_client_from_request

from core.pagination import paginate


def _doc_label(doc_type: str) -> str:
    return {
        DocumentType.INVOICE: "Invoice",
        DocumentType.ESTIMATE: "Estimate",
        DocumentType.PROPOSAL: "Proposal",
    }.get(doc_type, "Document")


def _staff_scoped_queryset(employee, qs):
    # Managers/admin/owner see all company docs
    if employee and employee.role in {EmployeeRole.MANAGER, EmployeeRole.ADMIN, EmployeeRole.OWNER}:
        return qs

    # Staff: see docs tied to projects assigned to them OR docs they created
    return qs.filter(
        Q(created_by=employee) |
        Q(project__assigned_to=employee)
    )


@company_context_required
def document_list(request, doc_type: str):
    company = request.active_company
    employee = request.active_employee

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = Document.objects.filter(company=company, doc_type=doc_type, deleted_at__isnull=True).select_related("client", "project")

    qs = _staff_scoped_queryset(employee, qs)

    if q:
        qs = qs.filter(
            Q(number__icontains=q)
            | Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(client__first_name__icontains=q)
            | Q(client__last_name__icontains=q)
            | Q(client__company_name__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)

    qs = qs.order_by("-created_at")

    paged = paginate(request, qs)

    ctx = {
        "doc_type": doc_type,
        "doc_label": _doc_label(doc_type),
        "q": q,
        "status": status,
        "documents": paged.object_list,
        "paginator": paged.paginator,
        "page_obj": paged.page_obj,
        "per_page": paged.per_page,
        "status_choices": DocumentStatus.choices,
    }
    return render(request, "documents/document_list.html", ctx)


@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def document_wizard(request, doc_type: str):
    company = request.active_company
    employee = request.active_employee

    if request.method == "POST":
        form = DocumentWizardForm(company=company, doc_type=doc_type, data=request.POST)
        if form.is_valid():
            mode = form.cleaned_data["mode"]
            template = form.cleaned_data.get("template")
            copy_from = form.cleaned_data.get("copy_from")

            with transaction.atomic():
                if mode == "copy" and copy_from:
                    doc = Document.objects.get(pk=copy_from.pk)
                    doc.pk = None
                    doc.id = None
                    doc.created_at = timezone.now()
                    doc.updated_at = timezone.now()
                    doc.deleted_at = None
                    doc.created_by = employee
                    doc.company = company
                    doc.doc_type = doc_type
                    doc.client = None
                    doc.project = None
                    doc.number = ""
                    doc.status = DocumentStatus.DRAFT
                    doc.notes = ""
                    doc.save()

                    # copy line items
                    items = DocumentLineItem.objects.filter(document=copy_from, deleted_at__isnull=True).order_by("sort_order", "created_at")
                    for li in items:
                        li.pk = None
                        li.id = None
                        li.created_at = timezone.now()
                        li.updated_at = timezone.now()
                        li.deleted_at = None
                        li.document = doc
                        li.save()

                    recalc_document_totals(doc)
                    log_event(company=company, actor=employee, event_type=f"{doc_type}.copied", object_type="Document", object_id=str(doc.id), summary=f"Copied {_doc_label(doc_type)}")
                    messages.success(request, f"Copied {_doc_label(doc_type).lower()} draft created.")
                    return redirect("documents:%s_edit" % doc_type, pk=doc.pk)

                # new document
                doc = Document.objects.create(
                    company=company,
                    doc_type=doc_type,
                    created_by=employee,
                    status=DocumentStatus.DRAFT,
                )

                # Composer defaults
                try:
                    doc.sales_tax_percent = getattr(company, "default_sales_tax_percent", Decimal("0.000")) or Decimal("0.000")
                except Exception:
                    doc.sales_tax_percent = Decimal("0.000")

                # Phase 5B: sensible date defaults
                today = timezone.localdate()
                if doc_type == DocumentType.INVOICE:
                    try:
                        due_days = int(getattr(company, "default_invoice_due_days", 30) or 30)
                    except Exception:
                        due_days = 30
                    doc.issue_date = today
                    doc.due_date = today + timedelta(days=due_days)
                else:
                    try:
                        valid_days = int(getattr(company, "default_estimate_valid_days", 30) or 30)
                    except Exception:
                        valid_days = 30
                    doc.issue_date = today
                    doc.valid_until = today + timedelta(days=valid_days)
                doc.save(update_fields=["issue_date", "due_date", "valid_until", "updated_at"])

                if template:
                    doc.title = template.name
                    doc.notes = template.notes_default or ""
                    doc.header_text = template.header_text or ""
                    doc.footer_text = template.footer_text or ""
                    doc.save(update_fields=["title", "notes", "header_text", "footer_text", "updated_at"])

                log_event(company=company, actor=employee, event_type=f"{doc_type}.created", object_type="Document", object_id=str(doc.id), summary=f"Created {_doc_label(doc_type)}")
                messages.success(request, f"{_doc_label(doc_type)} draft created.")
                return redirect("documents:%s_edit" % doc_type, pk=doc.pk)
    else:
        form = DocumentWizardForm(company=company, doc_type=doc_type)

    return render(
        request,
        "documents/document_wizard.html",
        {
            "doc_type": doc_type,
            "doc_label": _doc_label(doc_type),
            "form": form,
        },
    )


@company_context_required
def document_edit(request, doc_type: str, pk):
    company = request.active_company
    employee = request.active_employee

    doc = get_object_or_404(Document, pk=pk, company=company, doc_type=doc_type, deleted_at__isnull=True)
    # enforce staff access
    if employee.role == EmployeeRole.STAFF:
        if not (doc.created_by_id == employee.id or (doc.project_id and doc.project and doc.project.assigned_to_id == employee.id)):
            messages.error(request, "You do not have access to that document.")
            return redirect("documents:%s_list" % doc_type)

    can_edit = employee.role in {EmployeeRole.MANAGER, EmployeeRole.ADMIN, EmployeeRole.OWNER} or doc.created_by_id == employee.id
    if not can_edit:
        messages.error(request, "You do not have permission to edit this document.")
        return redirect("documents:%s_list" % doc_type)

    # Phase 6B: hard lock invoices once sent/paid/credited.
    if doc_type == DocumentType.INVOICE:
        try:
            if doc.is_invoice_locked() and request.method == "POST":
                messages.error(request, "This invoice is locked and cannot be edited.")
                return redirect("documents:%s_edit" % doc_type, pk=doc.pk)
        except Exception:
            pass

    # UX: if an invoice is locked, render the edit screen in read-only mode.
    is_locked = False
    lock_reason = ""
    if doc_type == DocumentType.INVOICE:
        try:
            is_locked = bool(doc.is_invoice_locked())
            lock_reason = doc.invoice_lock_reason() or ""
        except Exception:
            is_locked = False
            lock_reason = ""

    if request.method == "POST":
        # Email action: validate & save, then send to client.
        if request.POST.get("action") == "send_email":
            form = DocumentForm(request.POST, instance=doc, company=company, doc_type=doc_type)
            formset = DocumentLineItemFormSet(
                request.POST,
                instance=doc,
                form_kwargs={
                    'company_default_taxable': bool(getattr(company, 'default_line_items_taxable', False)),
                    'company': company,
                },
            )
            if form.is_valid() and formset.is_valid():
                with transaction.atomic():
                    form.save()

                    instances = formset.save(commit=False)
                    for obj in formset.deleted_objects:
                        obj.soft_delete()
                    for inst in instances:
                        inst.document = doc
                        inst.save()
                    formset.save_m2m()

                    if not doc.number:
                        if not doc.issue_date:
                            doc.issue_date = timezone.localdate()
                            doc.save(update_fields=["issue_date", "updated_at"])
                        doc.number = allocate_document_number(company, doc_type)
                        doc.save(update_fields=["number", "updated_at"])

                    # If they are emailing, consider it "Sent".
                    if doc.status == DocumentStatus.DRAFT:
                        doc.status = DocumentStatus.SENT
                        doc.save(update_fields=["status", "updated_at"])

                    recalc_document_totals(doc)

                result = send_document_to_client_from_request(request, doc)
                if result.sent:
                    messages.success(request, f"Email sent to {result.to}.")
                else:
                    messages.error(request, result.message)
                return redirect("documents:%s_edit" % doc_type, pk=doc.pk)

            messages.error(request, "Please fix the errors before sending.")
            # Invoice extras: credit notes + client credit application UI
            credit_notes = []
            apply_credit_form = None
            client_credit_cents = 0
            can_apply_credit = False
            if doc_type == DocumentType.INVOICE and doc.client_id:
                try:
                    credit_notes = list(
                        CreditNote.objects.filter(invoice=doc, deleted_at__isnull=True).order_by("-created_at")
                    )
                except Exception:
                    credit_notes = []
                client_credit_cents = int(getattr(doc.client, "credit_cents", 0) or 0)
                try:
                    from payments.forms import ApplyClientCreditForm
                    apply_credit_form = ApplyClientCreditForm()
                    can_apply_credit = (
                        client_credit_cents > 0
                        and doc.status not in {DocumentStatus.DRAFT, DocumentStatus.VOID}
                        and doc.balance_due_effective_cents() > 0
                    )
                except Exception:
                    apply_credit_form = None

            ctx = {
                "company": company,
                "is_manager": employee and employee.role in {EmployeeRole.MANAGER, EmployeeRole.ADMIN, EmployeeRole.OWNER},
                "doc_type": doc_type,
                "doc_label": _doc_label(doc_type),
                "doc": doc,
                "form": form,
                "formset": formset,
                "credit_notes": credit_notes,
                "client_credit_cents": client_credit_cents,
                "can_apply_credit": can_apply_credit,
                "apply_credit_form": apply_credit_form,
                "is_locked": is_locked,
                "lock_reason": lock_reason,
            }

            return render(request, "documents/document_edit.html", ctx)


        # Invoice helper: convert approved, billable, unbilled time into a single line item.
        if doc_type == DocumentType.INVOICE and request.POST.get("action") == "add_unbilled_time":
            if not doc.project_id:
                messages.error(request, "Select a project on the invoice first.")
                return redirect("documents:%s_edit" % doc_type, pk=doc.pk)
            project = doc.project
            if not project:
                messages.error(request, "Project not found.")
                return redirect("documents:%s_edit" % doc_type, pk=doc.pk)

            qs = TimeEntry.objects.filter(
                company=company,
                project=project,
                billable=True,
                status=TimeStatus.APPROVED,
                billed_document__isnull=True,
                deleted_at__isnull=True,
            )
            total_minutes = sum(int(te.duration_minutes or 0) for te in qs)
            if total_minutes <= 0:
                messages.info(request, "No approved unbilled time found for this project.")
                return redirect("documents:%s_edit" % doc_type, pk=doc.pk)

            # Build a single line: qty hours with project hourly rate.
            hours = (Decimal(total_minutes) / Decimal("60")).quantize(Decimal("0.01"))
            unit_price_cents = int(project.hourly_rate_cents or 0)
            line_subtotal_cents = int(round(float(hours) * unit_price_cents))

            with transaction.atomic():
                # Ensure invoice has a number/issue_date before billing time.
                if not doc.number:
                    if not doc.issue_date:
                        doc.issue_date = timezone.localdate()
                        doc.save(update_fields=["issue_date", "updated_at"])
                    doc.number = allocate_document_number(company, doc_type)
                    doc.save(update_fields=["number", "updated_at"])

                DocumentLineItem.objects.create(
                    document=doc,
                    sort_order=9999,
                    name=f"Labor (unbilled time) · {project.name}",
                    description=f"Approved unbilled time added from project {project.project_number or ''}".strip(),
                    qty=hours,
                    unit_price_cents=unit_price_cents,
                    line_subtotal_cents=line_subtotal_cents,
                    tax_cents=0,
                    line_total_cents=line_subtotal_cents,
                    is_taxable=False,
                )

                # Mark time as billed and tie back to invoice.
                billed_at = timezone.now()
                qs.update(status=TimeStatus.BILLED, billed_document=doc, billed_at=billed_at)

                recalc_document_totals(doc)

                log_event(company=company, actor=employee, event_type="invoice.time_billed", object_type="Document", object_id=str(doc.id), summary="Billed time to invoice", payload={"minutes": total_minutes})

            messages.success(request, f"Added {total_minutes} minutes of unbilled time to the invoice.")
            return redirect("documents:%s_edit" % doc_type, pk=doc.pk)

        action = (request.POST.get("action") or "").strip()

        form = DocumentForm(request.POST, instance=doc, company=company, doc_type=doc_type)
        formset = DocumentLineItemFormSet(
            request.POST,
            instance=doc,
            form_kwargs={
                'company_default_taxable': bool(getattr(company, 'default_line_items_taxable', False)),
                'company': company,
            },
        )
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()

                instances = formset.save(commit=False)
                # handle deletions
                for obj in formset.deleted_objects:
                    obj.soft_delete()
                for inst in instances:
                    inst.document = doc
                    inst.save()
                formset.save_m2m()

                # allocate number if blank
                if not doc.number:
                    if not doc.issue_date:
                        doc.issue_date = timezone.localdate()
                        doc.save(update_fields=["issue_date", "updated_at"])
                    doc.number = allocate_document_number(company, doc_type)
                    doc.save(update_fields=["number", "updated_at"])

                recalc_document_totals(doc)

                log_event(company=company, actor=employee, event_type=f"{doc_type}.updated", object_type="Document", object_id=str(doc.id), summary=f"Updated {_doc_label(doc_type)}")
                messages.success(request, f"{_doc_label(doc_type)} saved.")
                return redirect("documents:%s_edit" % doc_type, pk=doc.pk)
    else:
        form = DocumentForm(instance=doc, company=company, doc_type=doc_type)
        formset = DocumentLineItemFormSet(
            instance=doc,
            form_kwargs={
                'company_default_taxable': bool(getattr(company, 'default_line_items_taxable', False)),
                'company': company,
            },
        )

        if is_locked:
            for f in form.fields.values():
                f.disabled = True
            for fform in formset.forms:
                for f in fform.fields.values():
                    f.disabled = True
    # Invoice extras: credit notes + client credit application UI
    credit_notes = []
    apply_credit_form = None
    client_credit_cents = 0
    can_apply_credit = False
    if doc_type == DocumentType.INVOICE and doc.client_id:
        try:
            credit_notes = list(
                CreditNote.objects.filter(invoice=doc, deleted_at__isnull=True).order_by("-created_at")
            )
        except Exception:
            credit_notes = []
        client_credit_cents = int(getattr(doc.client, "credit_cents", 0) or 0)
        try:
            from payments.forms import ApplyClientCreditForm
            apply_credit_form = ApplyClientCreditForm()
            can_apply_credit = (
                client_credit_cents > 0
                and doc.status not in {DocumentStatus.DRAFT, DocumentStatus.VOID}
                and doc.balance_due_effective_cents() > 0
            )
        except Exception:
            apply_credit_form = None

    ctx = {
        "company": company,
        "is_manager": employee and employee.role in {EmployeeRole.MANAGER, EmployeeRole.ADMIN, EmployeeRole.OWNER},
        "doc_type": doc_type,
        "doc_label": _doc_label(doc_type),
        "doc": doc,
        "form": form,
        "formset": formset,
        "credit_notes": credit_notes,
        "client_credit_cents": client_credit_cents,
        "can_apply_credit": can_apply_credit,
        "apply_credit_form": apply_credit_form,
        "is_locked": is_locked,
        "lock_reason": lock_reason,
    }

    return render(request, "documents/document_edit.html", ctx)



@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def invoice_apply_credit(request, pk):
    company = request.active_company
    employee = request.active_employee

    invoice = get_object_or_404(
        Document,
        pk=pk,
        company=company,
        doc_type=DocumentType.INVOICE,
        deleted_at__isnull=True,
    )

    if invoice.status == DocumentStatus.VOID:
        messages.error(request, "Cannot apply credit to a void invoice.")
        return redirect("documents:invoice_edit", pk=invoice.pk)

    if not invoice.client_id:
        messages.error(request, "This invoice has no client; cannot apply credit.")
        return redirect("documents:invoice_edit", pk=invoice.pk)

    from payments.forms import ApplyClientCreditForm
    from payments.services import apply_client_credit_to_invoice

    if request.method != "POST":
        return redirect("documents:invoice_edit", pk=invoice.pk)

    form = ApplyClientCreditForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please enter a valid credit amount.")
        return redirect("documents:invoice_edit", pk=invoice.pk)

    dollars = form.cleaned_data["amount_dollars"]
    memo = form.cleaned_data.get("memo") or ""
    cents = int(round(float(dollars) * 100))

    try:
        apply_client_credit_to_invoice(invoice, cents=cents, actor=employee, memo=memo)
        messages.success(request, "Client credit applied.")
    except Exception as e:
        messages.error(request, f"Unable to apply credit: {e}")

    return redirect("documents:invoice_edit", pk=invoice.pk)


@company_context_required
@require_min_role(EmployeeRole.MANAGER)


def _render_document_pdf_bytes(request, html: str) -> tuple[bytes | None, str | None]:
    """Best-effort HTML→PDF via optional WeasyPrint.

    Uses request base_url so relative static/media assets resolve in PDFs.

    Returns: (pdf_bytes, error_code)
      - error_code is one of: "not_installed", "render_failed".
    """
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        return None, "not_installed"
    try:
        base_url = request.build_absolute_uri("/")
        return HTML(string=html, base_url=base_url).write_pdf(), None
    except Exception:
        return None, "render_failed"


@company_context_required
def document_print(request, doc_type: str, pk):
    """HTML print preview for a document (matches PDF layout)."""
    company = request.active_company
    employee = request.active_employee

    doc = get_object_or_404(Document, id=pk, company=company, doc_type=doc_type, deleted_at__isnull=True)
    doc = _staff_scoped_queryset(employee, Document.objects.filter(id=doc.id)).select_related("client", "project").first() or doc

    items = DocumentLineItem.objects.filter(document=doc, deleted_at__isnull=True).order_by("sort_order", "created_at")
    ctx = {
        "doc": doc,
        "doc_type": doc_type,
        "doc_label": _doc_label(doc_type),
        "company": company,
        "client": doc.client,
        "project": doc.project,
        "items": items,
        "is_pdf": False,
        "generated_at": timezone.now(),
    }
    return render(request, "documents/document_pdf.html", ctx)


@company_context_required
def document_pdf(request, doc_type: str, pk):
    """Download a customer-facing PDF for Invoice / Estimate / Proposal."""
    company = request.active_company
    employee = request.active_employee

    doc = get_object_or_404(Document, id=pk, company=company, doc_type=doc_type, deleted_at__isnull=True)
    doc = _staff_scoped_queryset(employee, Document.objects.filter(id=doc.id)).select_related("client", "project").first() or doc

    items = DocumentLineItem.objects.filter(document=doc, deleted_at__isnull=True).order_by("sort_order", "created_at")

    html = render_to_string(
        "documents/document_pdf.html",
        {
            "doc": doc,
            "doc_type": doc_type,
            "doc_label": _doc_label(doc_type),
            "company": company,
            "client": doc.client,
            "project": doc.project,
            "items": items,
            "is_pdf": True,
            "generated_at": timezone.now(),
        },
        request=request,
    )

    pdf_bytes, pdf_err = _render_document_pdf_bytes(request, html)
    if not pdf_bytes:
        if pdf_err == "not_installed":
            messages.error(
                request,
                "PDF export requires WeasyPrint. Install it in this environment (plus system deps like Cairo/Pango) to enable PDF output.",
            )
        else:
            messages.error(
                request,
                "PDF export failed. This is usually caused by missing WeasyPrint system dependencies (Cairo/Pango) or an HTML/CSS rendering issue.",
            )
        return redirect(reverse(f"documents:{doc_type}_print", kwargs={"pk": doc.id}))

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    safe_num = (doc.number or "draft").replace("/", "-")
    resp["Content-Disposition"] = f'attachment; filename="{doc_type}_{safe_num}.pdf"'
    return resp
def document_delete(request, doc_type: str, pk):
    company = request.active_company
    employee = request.active_employee
    doc = get_object_or_404(Document, pk=pk, company=company, doc_type=doc_type, deleted_at__isnull=True)

    if request.method == "POST":
        doc.soft_delete()
        log_event(company=company, actor=employee, event_type=f"{doc_type}.deleted", object_type="Document", object_id=str(doc.id), summary=f"Deleted {_doc_label(doc_type)}")
        messages.success(request, f"{_doc_label(doc_type)} deleted.")
        return redirect("documents:%s_list" % doc_type)
    return render(
        request,
        "documents/document_delete.html",
        {"doc_type": doc_type, "doc_label": _doc_label(doc_type), "doc": doc},
    )


@company_context_required
@require_min_role(EmployeeRole.ADMIN)
def document_settings(request):
    company = request.active_company
    employee = request.active_employee

    scheme = ensure_numbering_scheme(company)
    if request.method == "POST":
        form = NumberingSchemeForm(request.POST, instance=scheme)
        if form.is_valid():
            form.save()
            log_event(company=company, actor=employee, event_type="documents.numbering.updated", object_type="NumberingScheme", object_id=str(scheme.id), summary="Updated numbering scheme")
            messages.success(request, "Document numbering saved.")
            return redirect("documents:document_settings")
    else:
        form = NumberingSchemeForm(instance=scheme)

    templates = DocumentTemplate.objects.filter(company=company, deleted_at__isnull=True).order_by("doc_type", "name")
    return render(
        request,
        "documents/document_settings.html",
        {
            "form": form,
            "templates": templates,
        },
    )



@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def credit_note_create(request, invoice_pk):
    company = request.active_company
    employee = request.active_employee
    invoice = get_object_or_404(
        Document,
        pk=invoice_pk,
        company=company,
        doc_type=DocumentType.INVOICE,
        deleted_at__isnull=True,
    )
    if invoice.status == DocumentStatus.VOID:
        messages.error(request, "Cannot create a credit note for a void invoice.")
        return redirect("documents:invoice_edit", pk=invoice.pk)

    if invoice.status == DocumentStatus.DRAFT:
        messages.error(request, "Send the invoice before creating a credit note.")
        return redirect("documents:invoice_edit", pk=invoice.pk)

    # Only allow credit notes once invoice has been sent (or beyond).
        messages.error(request, "Cannot create a credit note for a void invoice.")
        return redirect("documents:invoice_edit", pk=invoice.pk)

    if request.method == "POST":
        form = CreditNoteForm(request.POST)
        if form.is_valid():
            cn = form.save(commit=False)
            cn.company = company
            cn.invoice = invoice
            cn.created_by = employee
            cn.status = CreditNoteStatus.DRAFT
            if not cn.number:
                seq, _ = CreditNoteNumberSequence.objects.get_or_create(company=company)
                n = seq.next_number
                seq.next_number = n + 1
                seq.save(update_fields=['next_number'])
                cn.number = f"CN-{timezone.now().strftime('%Y%m')}-{n:04d}"
            cn.save()
            log_event(
                company=company,
                actor=employee,
                event_type="financial.credit_note.created",
                object_type="CreditNote",
                object_id=str(cn.id),
                summary=f"Created credit note {cn.number} for invoice {invoice.number or invoice.id}",
            )
            messages.success(request, "Credit note created (Draft).")
            return redirect("documents:invoice_edit", pk=invoice.pk)
    else:
        # default values: full credit of remaining balance_due_effective (capped)
        remaining = invoice.balance_due_effective_cents() if hasattr(invoice, "balance_due_effective_cents") else int(invoice.balance_due_cents or 0)
        initial = {
                        # preview number (reserved on save)
            "number": "",
            "subtotal_cents": max(0, remaining),
            "tax_cents": 0,
            "total_cents": max(0, remaining),
        }
        form = CreditNoteForm(initial=initial)

    return render(
        request,
        "documents/credit_note_form.html",
        {
            "invoice": invoice,
            "form": form,
        },
    )


@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def credit_note_post(request, pk):
    company = request.active_company
    employee = request.active_employee
    cn = get_object_or_404(CreditNote, pk=pk, company=company, deleted_at__isnull=True)
    invoice = cn.invoice
    if not invoice or invoice.status in {DocumentStatus.DRAFT, DocumentStatus.VOID}:
        messages.error(request, "Send the invoice before posting a credit note.")
        return redirect("documents:invoice_edit", pk=getattr(invoice, "pk", cn.invoice_id))
    if cn.status != CreditNoteStatus.DRAFT:
        messages.info(request, "Credit note already posted.")
        return redirect("documents:invoice_edit", pk=cn.invoice_id)

    if request.method == "POST":
        from accounting.services import post_credit_note_if_needed

        entry = post_credit_note_if_needed(cn)
        if entry:
            messages.success(request, "Credit note posted.")
        else:
            messages.error(request, "Unable to post credit note.")
        return redirect("documents:invoice_edit", pk=cn.invoice_id)

    return render(
        request,
        "documents/credit_note_post_confirm.html",
        {"credit_note": cn},
    )



@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def credit_note_edit(request, pk):
    company = request.active_company
    employee = request.active_employee
    cn = get_object_or_404(CreditNote, pk=pk, company=company, deleted_at__isnull=True)

    if cn.status != CreditNoteStatus.DRAFT:
        messages.info(request, "Posted credit notes are read-only.")
        return redirect("documents:invoice_edit", pk=cn.invoice_id)

    invoice = cn.invoice
    if not invoice or invoice.status in {DocumentStatus.DRAFT, DocumentStatus.VOID}:
        messages.error(request, "Send the invoice before editing a credit note.")
        return redirect("documents:invoice_edit", pk=getattr(invoice, "pk", cn.invoice_id))

    initial = {
        "number": cn.number or "",
        "subtotal": f"{(cn.subtotal_cents or 0)/100:.2f}",
        "tax": f"{(cn.tax_cents or 0)/100:.2f}",
        "total": f"{(cn.total_cents or 0)/100:.2f}",
        "reason": cn.reason or "",
    }

    if request.method == "POST":
        form = CreditNoteForm(request.POST)
        if form.is_valid():
            data = form.to_model_values()
            cn.number = data.get("number") or cn.number
            cn.subtotal_cents = data["subtotal_cents"]
            cn.tax_cents = data["tax_cents"]
            cn.total_cents = data["total_cents"]
            cn.reason = data.get("reason", "")
            cn.save(update_fields=["number", "subtotal_cents", "tax_cents", "total_cents", "reason", "updated_at"])

            log_event(
                company=company,
                actor=employee,
                event_type="financial.credit_note.updated",
                object_type="CreditNote",
                object_id=str(cn.id),
                summary=f"Updated credit note {cn.number}",
            )
            messages.success(request, "Credit note updated.")
            return redirect("documents:invoice_edit", pk=invoice.pk)
    else:
        form = CreditNoteForm(initial=initial)

    return render(
        request,
        "documents/credit_note_form.html",
        {
            "invoice": invoice,
            "form": form,
            "credit_note": cn,
            "is_edit": True,
        },
    )

# --------------------------------------------------------------------------------------
# Client Statements (Phase 7H30)
# --------------------------------------------------------------------------------------

from django.http import HttpResponse
from django.template.loader import render_to_string


def _money(cents: int) -> str:
    try:
        return f"{(int(cents or 0) / 100):,.2f}"
    except Exception:
        return "0.00"


def _parse_iso_date(val: str | None):
    if not val:
        return None
    v = str(val).strip()
    if not v:
        return None
    try:
        from datetime import date as _date
        y, m, d = v.split('-')
        return _date(int(y), int(m), int(d))
    except Exception:
        return None


def _statement_rows(company, client, *, date_from=None, date_to=None):
    qs = (
        Document.objects.filter(
            company=company,
            doc_type=DocumentType.INVOICE,
            client=client,
            deleted_at__isnull=True,
        )
        .exclude(status__in=[DocumentStatus.PAID, DocumentStatus.VOID])
        .order_by("issue_date", "created_at")
    )

    # Optional date-range filtering (applies to issue_date when present; falls back to created_at date)
    if date_from:
        qs = qs.filter(
            Q(issue_date__gte=date_from) | Q(issue_date__isnull=True, created_at__date__gte=date_from)
        )
    if date_to:
        qs = qs.filter(
            Q(issue_date__lte=date_to) | Q(issue_date__isnull=True, created_at__date__lte=date_to)
        )


    rows = []
    total_due = 0
    for inv in qs:
        balance_eff = inv.balance_due_effective_cents()
        total_due += balance_eff
        rows.append(
            {
                "invoice": inv,
                "total": int(inv.total_cents or 0),
                "paid": int(inv.amount_paid_cents or 0),
                "credit_notes": int(inv.credit_applied_cents() or 0),
                "credit_apps": int(inv.credit_applications_cents() or 0),
                "balance": int(balance_eff),
                "total_display": _money(int(inv.total_cents or 0)),
                "paid_display": _money(int(inv.amount_paid_cents or 0)),
                "credits_display": _money(int((inv.credit_applied_cents() or 0) + (inv.credit_applications_cents() or 0))),
                "balance_display": _money(int(balance_eff)),
            }
        )
    return rows, total_due


@company_context_required
@require_min_role(EmployeeRole.MANAGER)


@company_context_required
def collections_followups_due(request):
    """Company-wide queue of collections follow-ups due (open notes with follow_up_on <= today).

    Phase 7H47:
    - Provide a lightweight, actionable queue for collections follow-ups.
    """

    company = request.active_company
    today = timezone.localdate()
    q = (request.GET.get("q") or "").strip()

    qs = (
        ClientCollectionsNote.objects.filter(
            company=company,
            status=CollectionsNoteStatus.OPEN,
            follow_up_on__isnull=False,
            follow_up_on__lte=today,
        )
        .select_related("client", "created_by")
        .order_by("follow_up_on", "client__name", "-created_at")
    )

    if q:
        qs = qs.filter(Q(client__name__icontains=q) | Q(note__icontains=q))

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    return render(
        request,
        "documents/collections_followups_due.html",
        {"page_obj": page_obj, "today": today, "q": q},
    )


def _weasyprint_is_installed() -> bool:
    try:
        import weasyprint  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def client_statement(request, client_pk):
    company = request.active_company
    client = get_object_or_404(Client, id=client_pk, company=company, deleted_at__isnull=True)

    activity = None
    # Phase 7H44: record statement view history (best-effort; never blocks).
    try:
        activity, _ = ClientStatementActivity.objects.get_or_create(company=company, client=client)
        activity.last_viewed_at = timezone.now()
        activity.last_viewed_by = getattr(request, "active_employee", None)
        activity.save(update_fields=["last_viewed_at", "last_viewed_by", "updated_at"])
    except Exception:
        pass

    date_from = _parse_iso_date(request.GET.get('date_from'))
    date_to = _parse_iso_date(request.GET.get('date_to'))

    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    rows, total_due = _statement_rows(company, client, date_from=date_from, date_to=date_to)

    qs_params = []
    if date_from:
        qs_params.append(f"date_from={date_from.isoformat()}")
    if date_to:
        qs_params.append(f"date_to={date_to.isoformat()}")
    querystring = ("?" + "&".join(qs_params)) if qs_params else ""

    site_base_url = getattr(settings, "SITE_BASE_URL", "").strip()
    weasyprint_installed = _weasyprint_is_installed()

    # Phase 7H35/7H38: default recipient comes from (1) last-used session value,
    # then (2) stored preference, then (3) client email.
    pref = ClientStatementRecipientPreference.objects.filter(company=company, client=client).first()
    initial_to_email = (request.session.get(f"stmt_to_{client.id}") or (pref.last_to_email if pref else "") or client.email or "").strip()

    # Phase 7H38: cadence helper suggestions and recent sent reminders.
    today = timezone.localdate()

    def _next_weekday(start: date, weekday: int) -> date:
        # weekday: Monday=0..Sunday=6
        delta = (weekday - start.weekday()) % 7
        return start if delta == 0 else (start + timedelta(days=delta))

    suggestions = [
        {"label": "In 3 days", "date": (today + timedelta(days=3))},
        {"label": "In 7 days", "date": (today + timedelta(days=7))},
        {"label": "In 14 days", "date": (today + timedelta(days=14))},
        {"label": "Next Monday", "date": _next_weekday(today, 0)},
    ]
    # End of month (simple): first of next month - 1 day
    first_next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    end_of_month = first_next_month - timedelta(days=1)
    suggestions.append({"label": "End of month", "date": end_of_month})

    sent_reminders = (
        StatementReminder.objects
        .filter(company=company, client=client, status=StatementReminderStatus.SENT, deleted_at__isnull=True)
        .order_by("-sent_at", "-scheduled_for")[:5]
    )

    failed_reminders = (
        StatementReminder.objects
        .filter(company=company, client=client, status=StatementReminderStatus.FAILED, deleted_at__isnull=True)
        .order_by("-attempted_at", "-updated_at")[:10]
    )

    # Phase 7H46: collections notes + follow-up tasks.
    collections_notes = (
        ClientCollectionsNote.objects
        .filter(company=company, client=client, deleted_at__isnull=True)
        .select_related("created_by", "completed_by")
        .order_by("status", "-created_at")
    )
    collections_notes_recent = list(collections_notes[:15])
    collections_open_followups = (
        ClientCollectionsNote.objects
        .filter(
            company=company,
            client=client,
            status=CollectionsNoteStatus.OPEN,
            follow_up_on__isnull=False,
            deleted_at__isnull=True,
            follow_up_on__lte=today,
        )
        .count()
    )

    return render(
        request,
        "documents/client_statement.html",
        {
            "client": client,
            "activity": activity,
            "scheduled_reminders": StatementReminder.objects.filter(company=company, client=client, status=StatementReminderStatus.SCHEDULED, deleted_at__isnull=True).order_by("scheduled_for")[:20],
            "sent_reminders": sent_reminders,
            "failed_reminders": failed_reminders,
            "collections_notes": collections_notes_recent,
            "collections_open_followups": collections_open_followups,
            "cadence_suggestions": suggestions,
            "default_recipient_email": initial_to_email,
            "rows": rows,
            "total_due_cents": total_due,
            "total_due": _money(total_due),
            "site_base_url_missing": not bool(site_base_url),
            "weasyprint_missing": not bool(weasyprint_installed),
            "date_from": date_from,
            "date_to": date_to,
            "querystring": querystring,
            "initial_to_email": initial_to_email,
        },
    )


@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def client_statement_csv(request, client_pk):
    company = request.active_company
    client = get_object_or_404(Client, id=client_pk, company=company, deleted_at__isnull=True)

    activity = None
    # Phase 7H44: record statement view history (best-effort; never blocks).
    try:
        activity, _ = ClientStatementActivity.objects.get_or_create(company=company, client=client)
        activity.last_viewed_at = timezone.now()
        activity.last_viewed_by = getattr(request, "active_employee", None)
        activity.save(update_fields=["last_viewed_at", "last_viewed_by", "updated_at"])
    except Exception:
        pass


    date_from = _parse_iso_date(request.GET.get('date_from'))
    date_to = _parse_iso_date(request.GET.get('date_to'))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    rows, total_due = _statement_rows(company, client, date_from=date_from, date_to=date_to)

    import csv
    from io import StringIO

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["Invoice #", "Issue date", "Due date", "Status", "Total", "Paid", "Credit notes", "Credit applied", "Balance due"])
    for r in rows:
        inv = r["invoice"]
        w.writerow(
            [
                inv.number,
                inv.issue_date.isoformat() if inv.issue_date else "",
                inv.due_date.isoformat() if inv.due_date else "",
                inv.status,
                _money(r["total"]),
                _money(r["paid"]),
                _money(r["credit_notes"]),
                _money(r["credit_apps"]),
                _money(r["balance"]),
            ]
        )
    w.writerow([])
    w.writerow(["", "", "", "TOTAL DUE", "", "", "", "", _money(total_due)])

    resp = HttpResponse(buf.getvalue(), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="statement_{client.id}.csv"'
    return resp


def _render_statement_pdf_bytes(html: str) -> tuple[bytes | None, str | None]:
    """Best-effort HTML→PDF via optional WeasyPrint.

    Returns: (pdf_bytes, error_code)
      - error_code is one of: "not_installed", "render_failed".
    """
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        return None, "not_installed"
    try:
        return HTML(string=html).write_pdf(), None
    except Exception:
        return None, "render_failed"


@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def client_statement_pdf(request, client_pk):
    company = request.active_company
    client = get_object_or_404(Client, id=client_pk, company=company, deleted_at__isnull=True)

    activity = None
    # Phase 7H44: record statement view history (best-effort; never blocks).
    try:
        activity, _ = ClientStatementActivity.objects.get_or_create(company=company, client=client)
        activity.last_viewed_at = timezone.now()
        activity.last_viewed_by = getattr(request, "active_employee", None)
        activity.save(update_fields=["last_viewed_at", "last_viewed_by", "updated_at"])
    except Exception:
        pass


    date_from = _parse_iso_date(request.GET.get('date_from'))
    date_to = _parse_iso_date(request.GET.get('date_to'))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    rows, total_due = _statement_rows(company, client, date_from=date_from, date_to=date_to)

    # Keep recipient prefill consistent with the Statement page.
    pref = ClientStatementRecipientPreference.objects.filter(company=company, client=client).first()
    initial_to_email = (request.session.get(f"stmt_to_{client.id}") or (pref.last_to_email if pref else "") or client.email or "").strip()

    qs_params = []
    if date_from:
        qs_params.append(f"date_from={date_from.isoformat()}")
    if date_to:
        qs_params.append(f"date_to={date_to.isoformat()}")
    querystring = ("?" + "&".join(qs_params)) if qs_params else ""

    html = render_to_string(
        "documents/client_statement_pdf.html",
        {
            "client": client,
            "activity": activity,
            "scheduled_reminders": StatementReminder.objects.filter(company=company, client=client, status=StatementReminderStatus.SCHEDULED, deleted_at__isnull=True).order_by("scheduled_for")[:20],
            "default_recipient_email": initial_to_email,
            "company": company,
            "rows": rows,
            "total_due_cents": total_due,
            "total_due": _money(total_due),
            "date_from": date_from,
            "date_to": date_to,
            "querystring": querystring,
            "initial_to_email": initial_to_email,
            "generated_at": timezone.now(),
            "date_from": date_from,
            "date_to": date_to,
            "site_base_url": getattr(settings, "SITE_BASE_URL", "").strip(),
            "statement_path": reverse("documents:client_statement", kwargs={"client_pk": client.id}),
        },
    )
    pdf_bytes, pdf_err = _render_statement_pdf_bytes(html)
    if not pdf_bytes:
        if pdf_err == "not_installed":
            messages.error(
                request,
                "PDF export requires WeasyPrint. Install it in this environment (plus system deps like Cairo/Pango) to enable PDF output.",
            )
        else:
            messages.error(
                request,
                "PDF export failed. This is usually caused by missing WeasyPrint system dependencies (Cairo/Pango) or an HTML/CSS rendering issue.",
            )
        return redirect(f"{reverse('documents:client_statement', kwargs={'client_pk': client.id})}{querystring}")

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="statement_{client.id}.pdf"'
    return resp


@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def client_statement_email(request, client_pk):
    company = request.active_company
    employee = request.active_employee
    client = get_object_or_404(Client, id=client_pk, company=company, deleted_at__isnull=True)

    activity = None
    # Phase 7H44: record statement view history (best-effort; never blocks).
    try:
        activity, _ = ClientStatementActivity.objects.get_or_create(company=company, client=client)
        activity.last_viewed_at = timezone.now()
        activity.last_viewed_by = getattr(request, "active_employee", None)
        activity.save(update_fields=["last_viewed_at", "last_viewed_by", "updated_at"])
    except Exception:
        pass


    from .forms import StatementEmailForm
    from .services_statements import send_statement_to_client_from_request

    if request.method != "POST":
        base_url = reverse('documents:client_statement', kwargs={'client_pk': client.id})
        qs = request.GET.urlencode()
        return redirect(f"{base_url}{('?' + qs) if qs else ''}")

    post_data = request.POST.copy()
    test_myself = (post_data.get("test_myself") or "").strip() in {"1", "true", "yes", "on"}
    if test_myself:
        post_data["to_email"] = (getattr(request.user, "email", "") or "").strip()
    form = StatementEmailForm(post_data, client=client)
    if not form.is_valid():
        messages.error(request, "Please correct the email form.")
        qs_params = []
        if request.POST.get('date_from'):
            qs_params.append(f"date_from={request.POST.get('date_from')}")
        if request.POST.get('date_to'):
            qs_params.append(f"date_to={request.POST.get('date_to')}")
        querystring = ("?" + "&".join(qs_params)) if qs_params else ""
        base_url = reverse('documents:client_statement', kwargs={'client_pk': client.id})
        return redirect(f"{base_url}{querystring}")

    res = send_statement_to_client_from_request(
        request,
        company=company,
        client=client,
        to_email=form.cleaned_data.get("to_email") or None,
        date_from=form.cleaned_data.get('date_from'),
        date_to=form.cleaned_data.get('date_to'),
        attach_pdf=bool(form.cleaned_data.get('attach_pdf')),
        template_variant=form.cleaned_data.get('tone') or 'sent',
    )

    # Optional: email the acting user a copy (best-effort; never blocks primary send).
    if res.sent and bool(form.cleaned_data.get("email_me_copy")) and not test_myself:
        try:
            from .services_statements import send_statement_copy_to_actor

            actor_email = (getattr(request.user, "email", "") or "").strip()
            if actor_email and actor_email.lower() != (res.to or "").strip().lower():
                send_statement_copy_to_actor(
                    company=company,
                    client=client,
                    actor=getattr(request, "active_employee", None),
                    to_email=actor_email,
                    date_from=form.cleaned_data.get('date_from'),
                    date_to=form.cleaned_data.get('date_to'),
                    attach_pdf=bool(form.cleaned_data.get('attach_pdf')),
                )
        except Exception:
            pass
    if res.sent:
        messages.success(request, f"Statement emailed to {res.to}.")
    else:
        messages.error(request, res.message)

    # Persist last-used recipient per client (per company) for faster collections workflows.
    if res.sent and not test_myself and (res.to or '').strip():
        try:
            ClientStatementRecipientPreference.objects.update_or_create(
                company=company,
                client=client,
                defaults={
                    'last_to_email': (res.to or '').strip(),
                    'updated_at': timezone.now(),
                    'updated_by': request.user if getattr(request, 'user', None) and getattr(request.user, 'is_authenticated', False) else None,
                },
            )
        except Exception:
            pass

    qs_params = []
    if form.cleaned_data.get('date_from'):
        qs_params.append(f"date_from={form.cleaned_data['date_from'].isoformat()}")
    if form.cleaned_data.get('date_to'):
        qs_params.append(f"date_to={form.cleaned_data['date_to'].isoformat()}")
    querystring = ("?" + "&".join(qs_params)) if qs_params else ""

    base_url = reverse('documents:client_statement', kwargs={'client_pk': client.id})
    return redirect(f"{base_url}{querystring}")


@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def client_statement_email_preview(request, client_pk):
    """Return a best-effort preview of the statement email without sending it."""
    company = request.active_company
    client = get_object_or_404(Client, id=client_pk, company=company, deleted_at__isnull=True)

    activity = None
    # Phase 7H44: record statement view history (best-effort; never blocks).
    try:
        activity, _ = ClientStatementActivity.objects.get_or_create(company=company, client=client)
        activity.last_viewed_at = timezone.now()
        activity.last_viewed_by = getattr(request, "active_employee", None)
        activity.save(update_fields=["last_viewed_at", "last_viewed_by", "updated_at"])
    except Exception:
        pass


    date_from = _parse_iso_date(request.GET.get("date_from"))
    date_to = _parse_iso_date(request.GET.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    to_email = (request.GET.get("to_email") or client.email or "").strip()
    attach_pdf = str(request.GET.get("attach_pdf") or "").strip().lower() in {"1", "true", "yes", "on"}
    tone = (request.GET.get("tone") or "friendly").strip()

    from .services_statements import build_statement_email_preview

    preview = build_statement_email_preview(
        company=company,
        client=client,
        to_email=to_email or None,
        date_from=date_from,
        date_to=date_to,
        attach_pdf=attach_pdf,
        tone=tone if tone in {"friendly", "past_due"} else "friendly",
    )

    return JsonResponse(
        {
            "ok": preview.ok,
            "to": preview.to,
            "subject": preview.subject,
            "html": preview.html,
            "text": preview.text,
            "warnings": preview.warnings,
            "errors": preview.errors,
        }
    )


@login_required
@require_active_company
def client_statement_reminder_create(request, client_pk):
    company = request.company
    client = get_object_or_404(Client, pk=client_pk, company=company, deleted_at__isnull=True)

    if request.method != "POST":
        return redirect("documents:client_statement", client_pk=client.id)

    scheduled_for = request.POST.get("scheduled_for")
    recipient_email = (request.POST.get("recipient_email") or "").strip()
    attach_pdf = bool(request.POST.get("attach_pdf"))
    tone = (request.POST.get("tone") or "friendly").strip()

    date_from = request.POST.get("date_from") or None
    date_to = request.POST.get("date_to") or None

    if not scheduled_for:
        messages.error(request, "Choose a reminder date")
        return redirect("documents:client_statement", client_pk=client.id)

    try:
        from django.utils.dateparse import parse_date

        sched = parse_date(str(scheduled_for))
        if not sched:
            raise ValueError
        df = parse_date(str(date_from)) if date_from else None
        dt = parse_date(str(date_to)) if date_to else None
    except Exception:
        messages.error(request, "Invalid reminder date")
        return redirect("documents:client_statement", client_pk=client.id)

    actor = getattr(request, "employee_profile", None)
    StatementReminder.objects.create(
        company=company,
        client=client,
        scheduled_for=sched,
        recipient_email=recipient_email or (client.email or ""),
        date_from=df,
        date_to=dt,
        attach_pdf=attach_pdf,
        tone=tone if tone in {"friendly", "past_due"} else "friendly",
        created_by=actor,
        modified_by=actor,
        updated_by_user=request.user if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False) else None,
        status=StatementReminderStatus.SCHEDULED,
    )

    messages.success(request, "Reminder scheduled")
    return redirect("documents:client_statement", client_pk=client.id)


@company_context_required
def client_statement_reminder_cancel(request, client_pk, reminder_pk):
    company = request.company
    client = get_object_or_404(Client, pk=client_pk, company=company, deleted_at__isnull=True)
    reminder = get_object_or_404(StatementReminder, pk=reminder_pk, company=company, client=client, deleted_at__isnull=True)

    if request.method == "POST":
        actor = getattr(request, "employee_profile", None)
        reminder.status = StatementReminderStatus.CANCELED
        reminder.modified_by = actor
        reminder.updated_by_user = request.user if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False) else None
        reminder.save(update_fields=["status", "modified_by", "updated_by_user", "updated_at"])
        messages.success(request, "Reminder canceled")

    return redirect("documents:client_statement", client_pk=client.id)


@company_context_required
def client_statement_reminder_reschedule(request, client_pk, reminder_pk):
    """One-click reschedule for FAILED reminders.

    Intended workflow: staff see a failed attempt, then reschedule to a new date.
    """
    company = request.company
    client = get_object_or_404(Client, pk=client_pk, company=company, deleted_at__isnull=True)
    reminder = get_object_or_404(StatementReminder, pk=reminder_pk, company=company, client=client, deleted_at__isnull=True)

    if request.method != "POST":
        return redirect("documents:client_statement", client_pk=client.id)

    from django.utils.dateparse import parse_date

    scheduled_for = (request.POST.get("scheduled_for") or "").strip()
    sched = parse_date(scheduled_for) if scheduled_for else None
    if not sched:
        # Default reschedule is +7 days
        sched = timezone.localdate() + timedelta(days=7)

    actor = getattr(request, "employee_profile", None)
    reminder.scheduled_for = sched
    reminder.status = StatementReminderStatus.SCHEDULED
    reminder.last_error = ""
    reminder.sent_at = None
    reminder.modified_by = actor
    reminder.updated_by_user = request.user if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False) else None
    reminder.save(update_fields=["scheduled_for", "status", "last_error", "sent_at", "modified_by", "updated_by_user", "updated_at"])

    messages.success(request, f"Reminder rescheduled for {sched}.")
    return redirect("documents:client_statement", client_pk=client.id)


@company_context_required
def client_statement_reminder_retry_now(request, client_pk, reminder_pk):
    """Staff-only: retry sending a single reminder immediately.

    This is intentionally synchronous and best-effort for ops/support workflows.
    Always records an attempt timestamp/counter.
    """

    user = getattr(request, "user", None)
    if not user or not (user.is_staff or user.is_superuser):
        messages.error(request, "Staff access required.")
        return redirect("documents:client_statement", client_pk=client_pk)

    company = request.company
    client = get_object_or_404(Client, pk=client_pk, company=company, deleted_at__isnull=True)
    reminder = get_object_or_404(StatementReminder, pk=reminder_pk, company=company, client=client, deleted_at__isnull=True)

    if request.method != "POST":
        return redirect("documents:client_statement", client_pk=client.id)

    from documents.services_statements import send_statement_to_client

    try:
        # Always record an attempt timestamp/counter, regardless of success.
        actor = getattr(request, "employee_profile", None)
        reminder.attempted_at = timezone.now()
        reminder.attempt_count = int(getattr(reminder, "attempt_count", 0) or 0) + 1
        reminder.modified_by = actor
        reminder.updated_by_user = request.user if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False) else None
        reminder.save(update_fields=["attempted_at", "attempt_count", "modified_by", "updated_by_user", "updated_at"])

        res = send_statement_to_client(
            company=reminder.company,
            client=reminder.client,
            actor=reminder.created_by,
            to_email=reminder.recipient_email,
            date_from=reminder.date_from,
            date_to=reminder.date_to,
            attach_pdf=bool(reminder.attach_pdf),
            template_variant=getattr(reminder, "tone", "friendly") or "friendly",
        )

        if res.sent:
            reminder.status = StatementReminderStatus.SENT
            reminder.sent_at = timezone.now()
            reminder.last_error = ""
            reminder.save(update_fields=["status", "sent_at", "last_error", "updated_at"])
            messages.success(request, "Reminder sent.")
        else:
            reminder.status = StatementReminderStatus.FAILED
            reminder.last_error = res.message
            reminder.save(update_fields=["status", "last_error", "updated_at"])
            messages.error(request, f"Send failed: {res.message}")
    except Exception as exc:
        reminder.status = StatementReminderStatus.FAILED
        reminder.last_error = str(exc)[:2000]
        reminder.save(update_fields=["status", "last_error", "updated_at"])
        messages.error(request, f"Send failed: {exc}")

    return redirect("documents:client_statement", client_pk=client.id)


@company_context_required
def client_statement_collections_note_add(request, client_pk):
    """Add a collections note for a client.

    Phase 7H46: lightweight collections notes + follow-up tasks.
    """

    company = request.company
    client = get_object_or_404(Client, pk=client_pk, company=company, deleted_at__isnull=True)

    if request.method != "POST":
        return redirect("documents:client_statement", client_pk=client.id)

    note = (request.POST.get("note") or "").strip()
    follow_up_on_raw = (request.POST.get("follow_up_on") or "").strip()

    if not note:
        messages.error(request, "Note is required.")
        return redirect("documents:client_statement", client_pk=client.id)

    follow_up_on = None
    if follow_up_on_raw:
        try:
            from django.utils.dateparse import parse_date

            follow_up_on = parse_date(follow_up_on_raw)
        except Exception:
            follow_up_on = None

    actor = getattr(request, "employee_profile", None)

    ClientCollectionsNote.objects.create(
        company=company,
        client=client,
        note=note,
        follow_up_on=follow_up_on,
        status=CollectionsNoteStatus.OPEN,
        created_by=actor,
        updated_by_user=request.user if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False) else None,
    )

    messages.success(request, "Collections note added.")
    return redirect("documents:client_statement", client_pk=client.id)


@company_context_required
def client_statement_collections_note_done(request, client_pk, note_pk):
    """Mark a collections note as done."""

    company = request.company
    client = get_object_or_404(Client, pk=client_pk, company=company, deleted_at__isnull=True)
    note = get_object_or_404(ClientCollectionsNote, pk=note_pk, company=company, client=client, deleted_at__isnull=True)

    if request.method == "POST":
        actor = getattr(request, "employee_profile", None)
        note.status = CollectionsNoteStatus.DONE
        note.completed_at = timezone.now()
        note.completed_by = actor
        note.updated_by_user = request.user if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False) else None
        note.save(update_fields=["status", "completed_at", "completed_by", "updated_by_user", "updated_at"])
        messages.success(request, "Collections note marked done.")

    next_url = (request.POST.get("next") or "").strip()
    if next_url:
        return redirect(next_url)
    return redirect("documents:client_statement", client_pk=client.id)


@company_context_required
@require_min_role(EmployeeRole.MANAGER)
@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def statement_reminders_list(request):
    """Company-wide statement reminder queue.

    Phase 7H42: bulk actions for collections workflows.
    """
    company = request.active_company

    status = (request.GET.get("status") or "scheduled").strip().lower()
    q = (request.GET.get("q") or "").strip()

    qs = (
        StatementReminder.objects.filter(company=company, deleted_at__isnull=True)
        .select_related("client")
        .order_by("-scheduled_for", "-created_at")
    )

    if status and status != "all":
        if status in {"scheduled", "failed", "sent", "canceled"}:
            qs = qs.filter(status=status)

    if q:
        qs = qs.filter(
            Q(client__name__icontains=q)
            | Q(client__email__icontains=q)
            | Q(recipient_email__icontains=q)
        )

    # Lightweight delivery report (last 30 days).
    report_start = timezone.localdate() - timedelta(days=29)
    attempt_base = StatementReminder.objects.filter(
        company=company,
        deleted_at__isnull=True,
        attempted_at__isnull=False,
        attempted_at__date__gte=report_start,
    )
    by_day = (
        attempt_base.annotate(day=TruncDate("attempted_at"))
        .values("day")
        .annotate(
            sent=Count("id", filter=Q(status=StatementReminderStatus.SENT)),
            failed=Count("id", filter=Q(status=StatementReminderStatus.FAILED)),
        )
        .order_by("day")
    )

    report_days: list[dict] = []
    day_cursor = report_start
    by_day_map = {r["day"]: r for r in by_day}
    for _ in range(30):
        row = by_day_map.get(day_cursor)
        report_days.append(
            {
                "day": day_cursor,
                "sent": int((row or {}).get("sent") or 0),
                "failed": int((row or {}).get("failed") or 0),
            }
        )
        day_cursor = day_cursor + timedelta(days=1)

    # Bulk actions
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        ids = []
        for raw in request.POST.getlist("reminder_ids"):
            try:
                ids.append(str(raw))
            except Exception:
                continue
        ids = ids[:500]

        actor = getattr(request, "active_employee", None)
        now = timezone.now()

        # Staff-only actions (best-effort): allow Django staff OR company admin/owner.
        user = getattr(request, "user", None)
        is_privileged = bool(getattr(user, "is_staff", False)) or bool(actor and actor.role in {EmployeeRole.ADMIN, EmployeeRole.OWNER})

        if not ids:
            messages.info(request, "Select at least one reminder.")
        elif action == "cancel_selected":
            updated = (
                StatementReminder.objects.filter(company=company, id__in=ids, deleted_at__isnull=True)
                .exclude(status=StatementReminderStatus.CANCELED)
                .update(
                    status=StatementReminderStatus.CANCELED,
                    modified_by=actor,
                    updated_by_user=request.user
                    if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False)
                    else None,
                    updated_at=now,
                )
            )
            if updated:
                messages.success(request, f"Canceled {updated} reminder(s).")
            else:
                messages.info(request, "No reminders were canceled.")
        elif action == "reschedule_selected":
            from django.utils.dateparse import parse_date

            scheduled_for = (request.POST.get("scheduled_for") or "").strip()
            sched = parse_date(scheduled_for) if scheduled_for else None
            if not sched:
                messages.error(request, "Choose a valid reschedule date.")
            else:
                updated = StatementReminder.objects.filter(company=company, id__in=ids, deleted_at__isnull=True).update(
                    scheduled_for=sched,
                    status=StatementReminderStatus.SCHEDULED,
                    last_error="",
                    sent_at=None,
                    modified_by=actor,
                    updated_by_user=request.user
                    if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False)
                    else None,
                    updated_at=now,
                )
                if updated:
                    messages.success(request, f"Rescheduled {updated} reminder(s) for {sched}.")
                else:
                    messages.info(request, "No reminders were rescheduled.")
        elif action == "send_now_selected":
            if not is_privileged:
                messages.error(request, "You do not have permission to send reminders in bulk.")
            else:
                from documents.services_statements import send_statement_to_client

                sent = 0
                failed = 0
                processed = 0
                targets = (
                    StatementReminder.objects.select_related("company", "client")
                    .filter(company=company, id__in=ids, deleted_at__isnull=True)
                    .exclude(status=StatementReminderStatus.CANCELED)
                )
                for rem in targets[:200]:
                    processed += 1
                    try:
                        rem.attempted_at = timezone.now()
                        rem.attempt_count = int(getattr(rem, "attempt_count", 0) or 0) + 1
                        rem.save(update_fields=["attempted_at", "attempt_count", "updated_at"])

                        res = send_statement_to_client(
                            company=rem.company,
                            client=rem.client,
                            actor=actor,
                            to_email=rem.recipient_email,
                            date_from=rem.date_from,
                            date_to=rem.date_to,
                            attach_pdf=bool(rem.attach_pdf),
                            template_variant=getattr(rem, "tone", "friendly") or "friendly",
                        )
                        if res.sent:
                            rem.status = StatementReminderStatus.SENT
                            rem.sent_at = timezone.now()
                            rem.last_error = ""
                            rem.save(update_fields=["status", "sent_at", "last_error", "updated_at"])
                            sent += 1
                        else:
                            rem.status = StatementReminderStatus.FAILED
                            rem.last_error = (res.message or "")[:2000]
                            rem.save(update_fields=["status", "last_error", "updated_at"])
                            failed += 1
                    except Exception as exc:
                        rem.status = StatementReminderStatus.FAILED
                        rem.last_error = str(exc)[:2000]
                        rem.save(update_fields=["status", "last_error", "updated_at"])
                        failed += 1

                if processed:
                    messages.success(request, f"Send-now processed={processed} sent={sent} failed={failed}.")
                else:
                    messages.info(request, "No reminders were sent.")
        elif action == "send_now_filtered":
            if not is_privileged:
                messages.error(request, "You do not have permission to send reminders in bulk.")
            else:
                confirm = request.POST.get("confirm_send_now_filtered") == "1"
                if not confirm:
                    messages.error(request, "Confirm the checkbox to send reminders for the filtered set.")
                else:
                    from documents.services_statements import send_statement_to_client

                    sent = 0
                    failed = 0
                    processed = 0

                    filtered_targets = (
                        qs.exclude(status=StatementReminderStatus.CANCELED)
                        .filter(status__in=[StatementReminderStatus.SCHEDULED, StatementReminderStatus.FAILED])
                        .select_related("company", "client")
                    )

                    cap = 200
                    for rem in filtered_targets[:cap]:
                        processed += 1
                        try:
                            rem.attempted_at = timezone.now()
                            rem.attempt_count = int(getattr(rem, "attempt_count", 0) or 0) + 1
                            rem.save(update_fields=["attempted_at", "attempt_count", "updated_at"]) 

                            res = send_statement_to_client(
                                company=rem.company,
                                client=rem.client,
                                actor=actor,
                                to_email=rem.recipient_email,
                                date_from=rem.date_from,
                                date_to=rem.date_to,
                                attach_pdf=bool(rem.attach_pdf),
                                template_variant=getattr(rem, "tone", "friendly") or "friendly",
                            )
                            if res.sent:
                                rem.status = StatementReminderStatus.SENT
                                rem.sent_at = timezone.now()
                                rem.last_error = ""
                                rem.save(update_fields=["status", "sent_at", "last_error", "updated_at"]) 
                                sent += 1
                            else:
                                rem.status = StatementReminderStatus.FAILED
                                rem.last_error = (res.message or "")[:2000]
                                rem.save(update_fields=["status", "last_error", "updated_at"]) 
                                failed += 1
                        except Exception as exc:
                            rem.status = StatementReminderStatus.FAILED
                            rem.last_error = str(exc)[:2000]
                            rem.save(update_fields=["status", "last_error", "updated_at"]) 
                            failed += 1

                    if processed:
                        messages.success(request, f"Send-now filtered processed={processed} (cap={cap}) sent={sent} failed={failed}.")
                    else:
                        messages.info(request, "No reminders matched the filtered set.")
        else:
            messages.error(request, "Unknown bulk action.")

        qs_params = request.GET.urlencode()
        return redirect(f"{reverse('documents:statement_reminders')}" + (f"?{qs_params}" if qs_params else ""))

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    qs_no_page = request.GET.copy()
    qs_no_page.pop("page", None)

    return render(
        request,
        "documents/statement_reminders.html",
        {
            "items": list(page_obj.object_list),
            "page_obj": page_obj,
            "qs_no_page": qs_no_page.urlencode(),
            "status": status,
            "q": q,
            "status_choices": StatementReminderStatus.choices,
            "delivery_report_days": report_days,
            "delivery_report_start": report_start,
        },
    )
