from __future__ import annotations

import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from companies.decorators import company_context_required, require_min_role
from companies.models import EmployeeRole

from .s3_presign import build_private_key, presign_private_upload


@require_POST
@company_context_required
@require_min_role(EmployeeRole.MANAGER)
def presign_upload(request):
    """Return a presigned POST policy for direct uploads to private S3 media.

    This endpoint is deliberately narrow:
    - Private bucket only
    - Known 'kinds' only (expense_receipt, project_file)
    - Manager+ only

    POST JSON:
      {"kind": "expense_receipt"|"project_file", "filename": "...", "content_type": "...", "project_id": "..."}

    Response JSON:
      {"url": "...", "fields": {...}, "key": "..."}
    """

    if not getattr(settings, "USE_S3", False) or not getattr(settings, "S3_DIRECT_UPLOADS", False):
        return JsonResponse({"error": "direct_uploads_disabled"}, status=400)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    kind = (payload.get("kind") or "").strip()
    filename = (payload.get("filename") or "").strip()
    content_type = (payload.get("content_type") or "").strip()
    project_id = (payload.get("project_id") or "").strip() or None

    if kind not in {"expense_receipt", "project_file"}:
        return JsonResponse({"error": "invalid_kind"}, status=400)
    if not filename:
        return JsonResponse({"error": "missing_filename"}, status=400)

    company = request.active_company

    try:
        key = build_private_key(kind, company_id=str(company.id), project_id=project_id, filename=filename)
        res = presign_private_upload(key=key, filename=filename, content_type=content_type or None)
    except Exception as e:
        return JsonResponse({"error": "presign_failed", "detail": str(e)}, status=400)

    return JsonResponse({"url": res.url, "fields": res.fields, "key": res.key})
