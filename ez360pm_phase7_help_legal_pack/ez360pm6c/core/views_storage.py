from __future__ import annotations

import json

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

from companies.decorators import company_context_required
from companies.models import EmployeeRole

from projects.models import Project

from .services.s3_presign import (
    presign_private_upload_expense_receipt,
    presign_private_upload_project_file,
)


@require_POST
@company_context_required
def presign_private_upload(request: HttpRequest) -> JsonResponse:
    """Server-side generator for short-lived *presigned POST* policies.

    Why this exists:
    - Large uploads should not hit the web dyno.
    - Tenant + permission rules must be enforced by the app before granting an upload policy.

    Supported kinds:
    - expense_receipt
    - project_file (requires project_id)
    """

    if not getattr(settings, "USE_S3", False):
        return JsonResponse({"ok": False, "error": "S3 is not enabled."}, status=400)

    company = request.active_company
    employee = request.active_employee

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    kind = (payload.get("kind") or "").strip()
    filename = (payload.get("filename") or "").strip()
    content_type = (payload.get("content_type") or "application/octet-stream").strip()

    if not kind or not filename:
        return JsonResponse({"ok": False, "error": "Missing kind/filename."}, status=400)

    try:
        if kind == "expense_receipt":
            if employee.role not in (EmployeeRole.MANAGER, EmployeeRole.ADMIN, EmployeeRole.OWNER):
                return JsonResponse({"ok": False, "error": "Not allowed."}, status=403)
            post = presign_private_upload_expense_receipt(company_id=str(company.id), filename=filename, content_type=content_type)

        elif kind == "project_file":
            project_id = (payload.get("project_id") or "").strip()
            if not project_id:
                return JsonResponse({"ok": False, "error": "Missing project_id."}, status=400)

            project = Project.objects.filter(company=company, id=project_id, deleted_at__isnull=True).first()
            if not project:
                return JsonResponse({"ok": False, "error": "Project not found."}, status=404)

            # Project access: managers+ always; staff only if assigned.
            if employee.role == EmployeeRole.STAFF and project.assigned_to_id != employee.id:
                return JsonResponse({"ok": False, "error": "Not allowed."}, status=403)

            post = presign_private_upload_project_file(company_id=str(company.id), project_id=str(project.id), filename=filename, content_type=content_type)

        else:
            return JsonResponse({"ok": False, "error": "Unknown kind."}, status=400)

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "url": post.url,
            "fields": post.fields,
            "object_name": post.object_name,
            "expires_in": post.expires_in,
        }
    )
