from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from audit.services import log_event
from audit.models import AuditEvent
from companies.decorators import company_context_required, require_min_role
from companies.models import EmployeeRole
from projects.models import Project
from timetracking.models import TimeEntry, TimeStatus

from decimal import Decimal

from .forms import DocumentForm, DocumentLineItemFormSet, DocumentWizardForm, NumberingSchemeForm, CreditNoteForm
from .models import Document, DocumentLineItem, DocumentStatus, DocumentTemplate, DocumentType, NumberingScheme, CreditNote, CreditNoteStatus, CreditNoteNumberSequence
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
                    doc.save(update_fields=["title", "notes", "updated_at"])

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
            formset = DocumentLineItemFormSet(request.POST, instance=doc, form_kwargs={'company_default_taxable': bool(getattr(company, 'default_line_items_taxable', False))})
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
        formset = DocumentLineItemFormSet(request.POST, instance=doc, form_kwargs={'company_default_taxable': bool(getattr(company, 'default_line_items_taxable', False))})
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

                # Send-to-client action (save + send)
                if action == "send_email":
                    # If still draft, move to SENT so it's clearly issued.
                    if doc.status == DocumentStatus.DRAFT:
                        doc.status = DocumentStatus.SENT
                        doc.save(update_fields=["status", "updated_at"])

                    result = send_document_to_client(request, doc)
                    if result.sent:
                        messages.success(request, f"Email sent to {result.to}.")
                    else:
                        messages.error(request, result.message)
                    return redirect("documents:%s_edit" % doc_type, pk=doc.pk)

                log_event(company=company, actor=employee, event_type=f"{doc_type}.updated", object_type="Document", object_id=str(doc.id), summary=f"Updated {_doc_label(doc_type)}")
                messages.success(request, f"{_doc_label(doc_type)} saved.")
                return redirect("documents:%s_edit" % doc_type, pk=doc.pk)
    else:
        form = DocumentForm(instance=doc, company=company, doc_type=doc_type)
        formset = DocumentLineItemFormSet(instance=doc, form_kwargs={'company_default_taxable': bool(getattr(company, 'default_line_items_taxable', False))})

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
