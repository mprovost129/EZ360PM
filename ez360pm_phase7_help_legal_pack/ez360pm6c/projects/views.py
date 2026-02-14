from __future__ import annotations

from decimal import Decimal
import os

from django.contrib import messages
from django.conf import settings
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from audit.services import log_event
from companies.decorators import company_context_required, require_min_role
from companies.models import EmployeeRole
from timetracking.models import TimeEntry, TimeStatus

from core.pagination import paginate

from integrations.models import DropboxConnection, IntegrationConfig
from integrations.services import (
    build_dropbox_project_folder,
    dropbox_ensure_folder,
    dropbox_upload_bytes,
    dropbox_create_shared_link,
)

from .forms import ProjectForm, ProjectServiceFormSet, ProjectFileForm
from .models import Project, ProjectFile


def _cents_to_dollars(cents: int) -> Decimal:
    return (Decimal(int(cents or 0)) / Decimal('100')).quantize(Decimal('0.01'))


def _auto_project_number(company) -> str:
    n = Project.objects.filter(company=company, deleted_at__isnull=True).count() + 1
    return f"P-{n:05d}"


@company_context_required
def project_list(request):
    company = request.active_company
    employee = request.active_employee

    qs = Project.objects.filter(company=company, deleted_at__isnull=True)
    if employee.role == EmployeeRole.STAFF:
        qs = qs.filter(assigned_to=employee)

    qs = qs.select_related('client', 'assigned_to').annotate(
        total_minutes=Coalesce(
            Sum(
                'timeentry__duration_minutes',
                filter=Q(timeentry__deleted_at__isnull=True) & ~Q(timeentry__status=TimeStatus.VOID),
            ),
            0,
        ),
        unbilled_minutes=Coalesce(
            Sum(
                'timeentry__duration_minutes',
                filter=Q(timeentry__deleted_at__isnull=True) & ~Q(timeentry__status__in=[TimeStatus.BILLED, TimeStatus.VOID]),
            ),
            0,
        ),
    ).order_by('-updated_at')

    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(project_number__icontains=q)
            | Q(name__icontains=q)
            | Q(client__company_name__icontains=q)
            | Q(client__last_name__icontains=q)
            | Q(client__first_name__icontains=q)
        )

    paged = paginate(request, qs)
    return render(
        request,
        'projects/project_list.html',
        {
            'projects': paged.object_list,
            'q': q,
            'paginator': paged.paginator,
            'page_obj': paged.page_obj,
            'per_page': paged.per_page,
        },
    )


@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def project_create(request):
    company = request.active_company
    employee = request.active_employee

    if request.method == 'POST':
        form = ProjectForm(request.POST)
        formset = ProjectServiceFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            if not obj.project_number:
                obj.project_number = _auto_project_number(company)
            obj.updated_by_user = request.user
            obj.save()
            formset.instance = obj
            formset.save()
            log_event(company=company, actor=employee, event_type='project.created', object_type='Project', object_id=obj.id, summary=f"Created project {obj.project_number}")
            messages.success(request, 'Project created.')
            return redirect('projects:project_detail', pk=obj.id)
    else:
        form = ProjectForm()
        formset = ProjectServiceFormSet()

    return render(request, 'projects/project_form.html', {'form': form, 'formset': formset, 'mode': 'create'})


@company_context_required
def project_detail(request, pk):
    company = request.active_company
    employee = request.active_employee

    obj = get_object_or_404(Project, id=pk, company=company, deleted_at__isnull=True)
    if employee.role == EmployeeRole.STAFF and obj.assigned_to_id != employee.id:
        messages.error(request, 'You do not have access to that project.')
        return redirect('projects:project_list')

    time_qs = (
        TimeEntry.objects.filter(company=company, project=obj, deleted_at__isnull=True)
        .select_related('employee', 'client', 'project')
        .order_by('-started_at', '-updated_at')
    )

    totals = time_qs.aggregate(
        total_minutes=Coalesce(Sum('duration_minutes'), 0),
        unbilled_minutes=Coalesce(Sum('duration_minutes', filter=~Q(status=TimeStatus.BILLED) & ~Q(status=TimeStatus.VOID)), 0),
    )

    return render(
        request,
        'projects/project_detail.html',
        {
            'project': obj,
            'time_entries': time_qs[:200],
            'total_minutes': int(totals['total_minutes'] or 0),
            'unbilled_minutes': int(totals['unbilled_minutes'] or 0),
            '_cents_to_dollars': _cents_to_dollars,
        },
    )


@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def project_edit(request, pk):
    company = request.active_company
    employee = request.active_employee

    obj = get_object_or_404(Project, id=pk, company=company, deleted_at__isnull=True)
    before_assignee_id = obj.assigned_to_id

    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=obj)
        formset = ProjectServiceFormSet(request.POST, instance=obj)
        if form.is_valid() and formset.is_valid():
            obj = form.save(commit=False)
            if not obj.project_number:
                obj.project_number = _auto_project_number(company)
            obj.updated_by_user = request.user
            obj.save()
            formset.save()

            log_event(company=company, actor=employee, event_type='project.updated', object_type='Project', object_id=obj.id, summary=f"Updated project {obj.project_number}")

            if before_assignee_id != obj.assigned_to_id and obj.assigned_to_id:
                log_event(company=company, actor=employee, event_type='project.assigned', object_type='Project', object_id=obj.id, summary=f"Assigned project {obj.project_number} to {obj.assigned_to.username_public}")

            messages.success(request, 'Project updated.')
            return redirect('projects:project_detail', pk=obj.id)
    else:
        form = ProjectForm(instance=obj)
        formset = ProjectServiceFormSet(instance=obj)

    return render(request, 'projects/project_form.html', {'form': form, 'formset': formset, 'mode': 'edit', 'project': obj})


@company_context_required
@require_min_role(EmployeeRole.ADMIN)
def project_files_sync_dropbox(request, pk):
    company = request.active_company
    project = get_object_or_404(Project, id=pk, company=company, deleted_at__isnull=True)

    cfg = getattr(company, 'integration_config', None)
    conn = getattr(company, 'dropbox_connection', None)
    if not (cfg and cfg.use_dropbox_for_project_files and conn and conn.is_active and conn.access_token):
        messages.error(request, "Dropbox is not connected or not enabled for project files.")
        return redirect("projects:project_files", pk=project.id)

    folder = build_dropbox_project_folder(company, project)

    synced = 0
    skipped = 0
    failed = 0

    qs = ProjectFile.objects.filter(company=company, project=project, deleted_at__isnull=True).order_by("created_at")
    for pf in qs:
        if pf.dropbox_shared_url:
            skipped += 1
            continue
        if not pf.file:
            skipped += 1
            continue
        try:
            # Read local file bytes
            with pf.file.open("rb") as f:
                content_bytes = f.read()
            if not content_bytes:
                skipped += 1
                continue

            dropbox_ensure_folder(conn.access_token, folder)
            original_name = os.path.basename(pf.file.name) or "file"
            safe_name = original_name.replace('\\', '_').replace('/', '_')
            dropbox_path = f"{folder}/{safe_name}"

            meta = dropbox_upload_bytes(conn.access_token, dropbox_path=dropbox_path, content=content_bytes)
            actual_path = str(meta.get('path_display') or meta.get('path_lower') or dropbox_path)
            shared = dropbox_create_shared_link(conn.access_token, dropbox_path=actual_path)

            pf.storage_backend = 'dropbox'
            pf.dropbox_path = actual_path
            pf.dropbox_shared_url = shared
            pf.save(update_fields=['storage_backend','dropbox_path','dropbox_shared_url','updated_at','revision'])
            synced += 1
        except Exception:
            failed += 1

    messages.success(request, f"Dropbox sync complete: {synced} synced, {skipped} skipped, {failed} failed.")
    return redirect("projects:project_files", pk=project.id)


@require_min_role(EmployeeRole.MANAGER)
def project_delete(request, pk):
    company = request.active_company
    employee = request.active_employee

    obj = get_object_or_404(Project, id=pk, company=company, deleted_at__isnull=True)

    if request.method == 'POST':
        obj.soft_delete()
        obj.updated_by_user = request.user
        obj.save(update_fields=['deleted_at', 'updated_by_user', 'updated_at'])
        log_event(company=company, actor=employee, event_type='project.deleted', object_type='Project', object_id=obj.id, summary=f"Deleted project {obj.project_number}")
        messages.success(request, 'Project deleted.')
        return redirect('projects:project_list')

    return render(request, 'projects/project_delete.html', {'project': obj})



@company_context_required
def project_files(request, pk):
    company = request.active_company
    employee = request.active_employee
    project = get_object_or_404(Project, id=pk, company=company, deleted_at__isnull=True)

    if employee.role == EmployeeRole.STAFF and project.assigned_to_id != employee.id:
        messages.error(request, 'You do not have access to that project.')
        return redirect('projects:project_list')

    qs = ProjectFile.objects.filter(company=company, project=project, deleted_at__isnull=True).select_related("uploaded_by").order_by("-created_at")

    if request.method == "POST":
        form = ProjectFileForm(request.POST, request.FILES)
        if form.is_valid():
            pf = form.save(commit=False)
            pf.company = company
            pf.project = project
            pf.uploaded_by = employee
            pf.updated_by_user = request.user

            # Phase 6D: if the browser uploaded directly to S3, it will post back
            # the storage-relative key in file_s3_key and we should NOT read from request.FILES.
            s3_key = (form.cleaned_data.get("file_s3_key") or "").strip()
            upload = request.FILES.get('file')
            content_bytes = b''
            if s3_key:
                pf.file.name = s3_key
            else:
                content_bytes = upload.read() if upload else b''

            pf.save()

            # Optional: also upload to Dropbox if connected + enabled
            try:
                cfg = getattr(company, 'integration_config', None)
                conn = getattr(company, 'dropbox_connection', None)
                if cfg and cfg.use_dropbox_for_project_files and conn and conn.is_active and conn.access_token and content_bytes:
                    original_name = upload.name if upload else 'file'
                    safe_name = original_name.replace('\\', '_').replace('/', '_')
                    folder = build_dropbox_project_folder(company, project)
                    dropbox_ensure_folder(conn.access_token, folder)
                    dropbox_path = f"{folder}/{safe_name}"
                    meta = dropbox_upload_bytes(conn.access_token, dropbox_path=dropbox_path, content=content_bytes)
                    actual_path = str(meta.get('path_display') or meta.get('path_lower') or dropbox_path)
                    shared = dropbox_create_shared_link(conn.access_token, dropbox_path=actual_path)
                    pf.storage_backend = 'dropbox'
                    pf.dropbox_path = actual_path
                    pf.dropbox_shared_url = shared
                    pf.save(update_fields=['storage_backend','dropbox_path','dropbox_shared_url','updated_at','revision'])
            except Exception as e:
                # Do not block local file storage
                messages.warning(request, f"Dropbox upload failed (saved locally): {e}")

            if s3_key and getattr(getattr(company, 'integration_config', None), 'use_dropbox_for_project_files', False):
                messages.info(request, "Direct-to-S3 upload succeeded. Dropbox auto-upload is skipped for direct uploads (no server-side file bytes).")

            log_event(
                request,
                action="project_file_created",
                entity_type="ProjectFile",
                entity_id=str(pf.id),
                message=f"Uploaded file to project {project.project_number or project.name}",
                payload={"project_id": str(project.id), "filename": pf.file.name, "title": pf.title},
            )
            messages.success(request, "File uploaded.")
            return redirect("projects:project_files", pk=project.id)
    else:
        form = ProjectFileForm()

    return render(
        request,
        "projects/project_files.html",
        {
            "project": project,
            "files": qs,
            "form": form,
            "dropbox_enabled": bool(getattr(getattr(company, "integration_config", None), "use_dropbox_for_project_files", False)),
            "dropbox_connected": bool(getattr(getattr(company, "dropbox_connection", None), "is_active", False)),
            "use_s3": bool(getattr(settings, "USE_S3", False)),
        },
    )


@require_min_role(EmployeeRole.MANAGER)
@company_context_required
def project_file_delete(request, pk, file_id):
    company = request.active_company
    project = get_object_or_404(Project, id=pk, company=company, deleted_at__isnull=True)
    pf = get_object_or_404(ProjectFile, id=file_id, company=company, project=project, deleted_at__isnull=True)

    if request.method == "POST":
        pf.soft_delete()
        pf.updated_by_user = request.user
        pf.save(update_fields=["deleted_at", "updated_by_user", "updated_at", "revision"])
        log_event(
            request,
            action="project_file_deleted",
            entity_type="ProjectFile",
            entity_id=str(pf.id),
            message=f"Deleted project file on {project.project_number or project.name}",
            payload={"project_id": str(project.id), "filename": pf.file.name, "title": pf.title},
        )
        messages.success(request, "File removed.")
        return redirect("projects:project_files", pk=project.id)

    return render(request, "projects/project_file_confirm_delete.html", {"project": project, "file": pf})


@company_context_required
def project_file_open(request, pk, file_id):
    company = request.active_company
    employee = request.active_employee
    project = get_object_or_404(Project, id=pk, company=company, deleted_at__isnull=True)
    pf = get_object_or_404(ProjectFile, id=file_id, company=company, project=project, deleted_at__isnull=True)

    if employee.role == EmployeeRole.STAFF and project.assigned_to_id != employee.id:
        messages.error(request, "You do not have access to that project.")
        return redirect("projects:project_list")

    if pf.dropbox_shared_url:
        # Force download/open via Dropbox by setting dl=1 when possible
        url = pf.dropbox_shared_url
        if "dl=0" in url:
            url = url.replace("dl=0", "dl=1")
        elif "?" not in url:
            url = url + "?dl=1"
        return redirect(url)

    return redirect(pf.file.url)
