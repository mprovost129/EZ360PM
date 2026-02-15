from __future__ import annotations

import csv
from io import StringIO

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from audit.services import log_event
from companies.decorators import company_context_required, require_min_role
from companies.models import EmployeeRole
from projects.models import Project

from core.pagination import paginate

from .forms import (
    CLIENT_EXPORT_FIELDS,
    ClientForm,
    ClientImportUploadWizardForm,
    ClientImportMapWizardForm,
    ClientPhoneFormSet,
    normalize_email,
    normalize_phone,
    normalize_state,
    normalize_text,
    normalize_zip,
    normalize_phone_type,
    suggest_client_mapping,
)
from .models import Client, ClientPhone, ClientImportBatch, ClientImportMapping


def _cents_to_dollars(cents: int) -> str:
    try:
        return f"{(int(cents or 0) / 100):,.2f}"
    except Exception:
        return "0.00"


def _visible_clients_qs(request: HttpRequest):
    company = request.active_company
    employee = request.active_employee

    qs = Client.objects.filter(company=company, deleted_at__isnull=True).prefetch_related("phones")

    # Staff: only see clients linked to assigned projects
    if employee.role == EmployeeRole.STAFF:
        project_client_ids = (
            Project.objects.filter(company=company, assigned_to=employee, deleted_at__isnull=True)
            .exclude(client__isnull=True)
            .values_list("client_id", flat=True)
            .distinct()
        )
        qs = qs.filter(id__in=list(project_client_ids))

    return qs


@company_context_required
def client_list(request: HttpRequest) -> HttpResponse:
    q = str(request.GET.get("q") or "").strip()

    qs = _visible_clients_qs(request)
    if q:
        qs = qs.filter(
            Q(company_name__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
        )

    paged = paginate(request, qs.order_by("company_name", "last_name", "first_name"))
    clients = paged.object_list

    # annotate display strings
    rows = []
    for c in clients:
        phones = [p for p in c.phones.all() if p.deleted_at is None]
        primary_phone = phones[0].number if phones else ""
        primary_contact = c.email or primary_phone
        rows.append(
            {
                "obj": c,
                "name": c.display_label(),
                "primary_contact": primary_contact,
                "credit": _cents_to_dollars(c.credit_cents),
                "outstanding": _cents_to_dollars(c.outstanding_cents),
            }
        )

    can_manage = request.active_employee.role in {EmployeeRole.MANAGER, EmployeeRole.ADMIN, EmployeeRole.OWNER}

    return render(
        request,
        "crm/clients_list.html",
        {
            "q": q,
            "rows": rows,
            "can_manage": can_manage,
            "paginator": paged.paginator,
            "page_obj": paged.page_obj,
            "per_page": paged.per_page,
        },
    )


@require_min_role(EmployeeRole.MANAGER)
@require_http_methods(["GET", "POST"])
def client_create(request: HttpRequest) -> HttpResponse:
    company = request.active_company

    if request.method == "POST":
        form = ClientForm(request.POST)
        formset = ClientPhoneFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                client = form.save(commit=False)
                client.company = company
                client.updated_by_user = request.user
                client.updated_at = timezone.now()
                client.revision += 1
                client.save()

                formset.instance = client
                formset.save()

                log_event(
                    company=company,
                    actor=request.active_employee,
                    event_type="client.created",
                    object_type="Client",
                    object_id=client.id,
                    summary=f"Created client: {client.display_label()}",
                    request=request,
                )

            messages.success(request, "Client created.")
            return redirect("crm:client_list")
    else:
        form = ClientForm()
        formset = ClientPhoneFormSet()

    return render(
        request,
        "crm/client_form.html",
        {
            "mode": "create",
            "form": form,
            "formset": formset,
        },
    )


@require_min_role(EmployeeRole.MANAGER)
@require_http_methods(["GET", "POST"])
def client_edit(request: HttpRequest, pk) -> HttpResponse:
    company = request.active_company

    client = get_object_or_404(Client, id=pk, company=company, deleted_at__isnull=True)

    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        formset = ClientPhoneFormSet(request.POST, instance=client)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                client = form.save(commit=False)
                client.updated_by_user = request.user
                client.updated_at = timezone.now()
                client.revision += 1
                client.save()
                formset.save()

                log_event(
                    company=company,
                    actor=request.active_employee,
                    event_type="client.updated",
                    object_type="Client",
                    object_id=client.id,
                    summary=f"Updated client: {client.display_label()}",
                    request=request,
                )

            messages.success(request, "Client updated.")
            return redirect("crm:client_list")
    else:
        form = ClientForm(instance=client)
        formset = ClientPhoneFormSet(instance=client)

    return render(
        request,
        "crm/client_form.html",
        {
            "mode": "edit",
            "client": client,
            "form": form,
            "formset": formset,
        },
    )


@require_min_role(EmployeeRole.MANAGER)
@require_http_methods(["GET", "POST"])
def client_delete(request: HttpRequest, pk) -> HttpResponse:
    company = request.active_company
    client = get_object_or_404(Client, id=pk, company=company, deleted_at__isnull=True)

    if request.method == "POST":
        with transaction.atomic():
            client.deleted_at = timezone.now()
            client.updated_by_user = request.user
            client.updated_at = timezone.now()
            client.revision += 1
            client.save(update_fields=["deleted_at", "updated_by_user", "updated_at", "revision"])

            log_event(
                company=company,
                actor=request.active_employee,
                event_type="client.deleted",
                object_type="Client",
                object_id=client.id,
                summary=f"Deleted client: {client.display_label()}",
                request=request,
            )

        messages.success(request, "Client deleted.")
        return redirect("crm:client_list")

    return render(request, "crm/client_delete.html", {"client": client})


@require_min_role(EmployeeRole.MANAGER)
@require_http_methods(["GET", "POST"])
def client_import(request: HttpRequest) -> HttpResponse:
    """Client import wizard (step 1): upload + preview.

    Step 2 (mapping + import) is handled by client_import_map.
    """

    company = request.active_company

    def _extract_headers_and_preview(csv_content: str, preview_rows: int = 10):
        reader = csv.DictReader(StringIO(csv_content))
        headers = [h for h in (reader.fieldnames or []) if h is not None]
        preview = []
        for i, row in enumerate(reader):
            if i >= preview_rows:
                break
            preview.append({str(k): str(v or "") for k, v in row.items()})
        return headers, preview

    if request.method == "POST":
        form = ClientImportUploadWizardForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data["csv_file"]
            content = f.read().decode("utf-8", errors="ignore")
            headers, preview = _extract_headers_and_preview(content)

            if not headers:
                messages.error(request, "CSV must include a header row.")
                return render(
                    request,
                    "crm/client_import_upload.html",
                    {"form": form, "headers": [], "preview": []},
                )

            batch = ClientImportBatch.objects.create(
                company=company,
                uploaded_by=request.user if request.user.is_authenticated else None,
                original_filename=getattr(f, "name", "") or "",
                csv_content=content,
            )

            return redirect("crm:client_import_map", batch_id=batch.id)
    else:
        form = ClientImportUploadWizardForm()
        headers, preview = [], []

    return render(
        request,
        "crm/client_import_upload.html",
        {"form": form, "headers": headers, "preview": preview},
    )


@require_min_role(EmployeeRole.MANAGER)
@require_http_methods(["GET", "POST"])
def client_import_map(request: HttpRequest, batch_id) -> HttpResponse:
    """Client import wizard (step 2): map columns + import."""

    company = request.active_company
    batch = get_object_or_404(ClientImportBatch, id=batch_id, company=company)

    def _extract_headers_and_preview(csv_content: str, preview_rows: int = 10):
        reader = csv.DictReader(StringIO(csv_content))
        headers = [h for h in (reader.fieldnames or []) if h is not None]
        preview = []
        for i, row in enumerate(reader):
            if i >= preview_rows:
                break
            preview.append({str(k): str(v or "") for k, v in row.items()})
        return headers, preview

    headers, preview = _extract_headers_and_preview(batch.csv_content)
    if not headers:
        messages.error(request, "This import batch has no headers. Please re-upload your CSV.")
        return redirect("crm:client_import")

    # Mapping selection priority:
    # 1) explicit mapping chosen via ?mapping=<id>
    # 2) company's default saved mapping
    # 3) header-based auto-suggestion
    selected_mapping_id = str(request.GET.get("mapping") or "").strip()
    selected_mapping: ClientImportMapping | None = None
    if selected_mapping_id:
        selected_mapping = ClientImportMapping.objects.filter(company=company, id=selected_mapping_id).first()
    if not selected_mapping:
        selected_mapping = ClientImportMapping.objects.filter(company=company, is_default=True).order_by("-updated_at").first()

    if selected_mapping and isinstance(selected_mapping.mapping, dict):
        initial_mapping = {str(k): str(v) for k, v in (selected_mapping.mapping or {}).items()}
    else:
        initial_mapping = suggest_client_mapping(headers)

    saved_mappings = list(ClientImportMapping.objects.filter(company=company).order_by("name"))

    if request.method == "POST":
        form = ClientImportMapWizardForm(request.POST, csv_headers=headers, initial_mapping=initial_mapping)
        if form.is_valid():
            mapping = form.cleaned_mapping()
            duplicate_policy = form.cleaned_data.get("duplicate_policy")

            # Optionally save mapping for reuse
            if form.cleaned_data.get("save_mapping"):
                mapping_name = normalize_text(form.cleaned_data.get("mapping_name") or "")
                set_as_default = bool(form.cleaned_data.get("set_as_default"))
                # If setting default, clear any existing default for company
                if set_as_default:
                    ClientImportMapping.objects.filter(company=company, is_default=True).update(is_default=False)
                obj, created = ClientImportMapping.objects.update_or_create(
                    company=company,
                    name=mapping_name,
                    defaults={
                        "mapping": mapping,
                        "is_default": set_as_default,
                        "updated_at": timezone.now(),
                        "updated_by": request.user,
                        "created_by": request.user,
                    },
                )
                if created:
                    messages.success(request, f"Saved mapping: {obj.name}")

            created_count = 0
            updated_count = 0
            skipped_count = 0
            error_count = 0

            report_out = StringIO()
            report_writer = csv.DictWriter(
                report_out,
                fieldnames=["row", "action", "client_id", "label", "email", "message"],
            )
            report_writer.writeheader()

            reader = csv.DictReader(StringIO(batch.csv_content))

            with transaction.atomic():
                for idx, raw in enumerate(reader, start=2):  # header is row 1
                    if not raw:
                        continue

                    try:
                        # Build canonical row dict using mapping
                        row: dict[str, str] = {}
                        for dest, src in mapping.items():
                            row[dest] = normalize_text(str(raw.get(src, "") or ""))

                        # Normalization pass
                        row["email"] = normalize_email(row.get("email", ""))
                        row["state"] = normalize_state(row.get("state", ""))
                        row["zip_code"] = normalize_zip(row.get("zip_code", ""))
                        row["phone1"] = normalize_phone(row.get("phone1", ""))
                        row["phone2"] = normalize_phone(row.get("phone2", ""))
                    except Exception as e:
                        error_count += 1
                        report_writer.writerow(
                            {
                                "row": idx,
                                "action": "error",
                                "client_id": "",
                                "label": "",
                                "email": "",
                                "message": f"Parse error: {e}",
                            }
                        )
                        continue

                    # Minimal emptiness check
                    if not any(v for v in row.values()):
                        continue

                    email = normalize_email(row.get("email") or "")
                    existing = None
                    if email:
                        existing = Client.objects.filter(company=company, deleted_at__isnull=True, email__iexact=email).first()

                    if existing and duplicate_policy == "skip":
                        skipped_count += 1
                        report_writer.writerow(
                            {
                                "row": idx,
                                "action": "skipped",
                                "client_id": str(existing.id),
                                "label": existing.display_label(),
                                "email": existing.email,
                                "message": "Email already exists",
                            }
                        )
                        continue

                    if existing and duplicate_policy == "update":
                        client = existing
                        client.company_name = row.get("company_name") or client.company_name
                        client.first_name = row.get("first_name") or client.first_name
                        client.last_name = row.get("last_name") or client.last_name
                        client.email = email or client.email
                        client.internal_note = row.get("internal_note") or client.internal_note
                        client.address1 = row.get("address1") or client.address1
                        client.address2 = row.get("address2") or client.address2
                        client.city = row.get("city") or client.city
                        if row.get("state"):
                            client.state = (row.get("state") or "")[:2]
                        if row.get("zip_code"):
                            client.zip_code = row.get("zip_code") or client.zip_code
                        client.updated_by_user = request.user
                        client.updated_at = timezone.now()
                        client.revision = (client.revision or 0) + 1
                        client.save()
                        updated_count += 1
                        report_writer.writerow(
                            {
                                "row": idx,
                                "action": "updated",
                                "client_id": str(client.id),
                                "label": client.display_label(),
                                "email": client.email,
                                "message": "Updated existing by email",
                            }
                        )
                    else:
                        client = Client(
                            company=company,
                            company_name=row.get("company_name", ""),
                            first_name=row.get("first_name", ""),
                            last_name=row.get("last_name", ""),
                            email=email,
                            internal_note=row.get("internal_note", ""),
                            address1=row.get("address1", ""),
                            address2=row.get("address2", ""),
                            city=row.get("city", ""),
                            state=(row.get("state", "") or "")[:2],
                            zip_code=(row.get("zip_code", "") or ""),
                            updated_by_user=request.user,
                            revision=1,
                        )
                        client.save()
                        created_count += 1
                        report_writer.writerow(
                            {
                                "row": idx,
                                "action": "created",
                                "client_id": str(client.id),
                                "label": client.display_label(),
                                "email": client.email,
                                "message": "Created new",
                            }
                        )

                    # Phones
                    phone1 = (row.get("phone1") or "").strip()
                    if phone1:
                        ClientPhone.objects.get_or_create(
                            client=client,
                            number=phone1,
                            defaults={
                                "phone_type": normalize_phone_type(row.get("phone1_type") or ""),
                                "revision": 1,
                                "updated_by_user": request.user,
                            },
                        )
                    phone2 = (row.get("phone2") or "").strip()
                    if phone2:
                        ClientPhone.objects.get_or_create(
                            client=client,
                            number=phone2,
                            defaults={
                                "phone_type": normalize_phone_type(row.get("phone2_type") or ""),
                                "revision": 1,
                                "updated_by_user": request.user,
                            },
                        )

                log_event(
                    company=company,
                    actor=request.active_employee,
                    event_type="client.import",
                    object_type="Client",
                    summary=f"Imported clients (created={created_count}, updated={updated_count}, skipped={skipped_count}, errors={error_count})",
                    payload={"created": created_count, "updated": updated_count, "skipped": skipped_count, "errors": error_count},
                    request=request,
                )

                # Persist results and report on batch (do not delete so report can be downloaded)
                batch.imported_at = timezone.now()
                batch.last_summary = {
                    "created": created_count,
                    "updated": updated_count,
                    "skipped": skipped_count,
                    "errors": error_count,
                    "duplicate_policy": duplicate_policy,
                    "mapping": mapping,
                }
                batch.last_report_csv = report_out.getvalue()
                batch.save(update_fields=["imported_at", "last_summary", "last_report_csv"])

            return redirect("crm:client_import_done", batch_id=batch.id)
    else:
        form = ClientImportMapWizardForm(csv_headers=headers, initial_mapping=initial_mapping)

    return render(
        request,
        "crm/client_import_map.html",
        {
            "batch": batch,
            "form": form,
            "headers": headers,
            "preview": preview,
            "saved_mappings": saved_mappings,
            "selected_mapping": selected_mapping,
        },
    )


@require_min_role(EmployeeRole.MANAGER)
@require_http_methods(["GET"])
def client_import_done(request: HttpRequest, batch_id) -> HttpResponse:
    company = request.active_company
    batch = get_object_or_404(ClientImportBatch, id=batch_id, company=company)
    summary = batch.last_summary or {}
    return render(
        request,
        "crm/client_import_done.html",
        {
            "batch": batch,
            "summary": summary,
        },
    )


@require_min_role(EmployeeRole.MANAGER)
@require_http_methods(["GET"])
def client_import_report_download(request: HttpRequest, batch_id) -> HttpResponse:
    company = request.active_company
    batch = get_object_or_404(ClientImportBatch, id=batch_id, company=company)
    if not (batch.last_report_csv or "").strip():
        messages.error(request, "No import report found for this batch.")
        return redirect("crm:client_import")

    filename = f"client_import_report_{batch_id}.csv"
    resp = HttpResponse(batch.last_report_csv, content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@require_min_role(EmployeeRole.MANAGER)
def client_export(request: HttpRequest) -> HttpResponse:
    company = request.active_company

    qs = _visible_clients_qs(request).order_by("company_name", "last_name", "first_name")

    # Build CSV in memory
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CLIENT_EXPORT_FIELDS)
    writer.writeheader()

    for c in qs:
        phones = [p for p in c.phones.all() if p.deleted_at is None]
        phone1 = phones[0] if len(phones) >= 1 else None
        phone2 = phones[1] if len(phones) >= 2 else None

        writer.writerow(
            {
                "company_name": c.company_name,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "email": c.email,
                "internal_note": c.internal_note,
                "address1": c.address1,
                "address2": c.address2,
                "city": c.city,
                "state": c.state,
                "zip_code": c.zip_code,
                "phone1": phone1.number if phone1 else "",
                "phone1_type": phone1.phone_type if phone1 else "",
                "phone2": phone2.number if phone2 else "",
                "phone2_type": phone2.phone_type if phone2 else "",
            }
        )

    log_event(
        company=company,
        actor=request.active_employee,
        event_type="client.export",
        object_type="Client",
        summary="Exported clients CSV",
        payload={"count": qs.count()},
        request=request,
    )

    resp = HttpResponse(output.getvalue(), content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="clients.csv"'
    return resp
