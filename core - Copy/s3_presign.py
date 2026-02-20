from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from django.conf import settings


_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    name = (name or "").strip() or "file"
    base = os.path.basename(name)
    base = base.replace(" ", "_")
    base = _FILENAME_SAFE_RE.sub("_", base)
    # Keep it reasonable
    return base[:180] if len(base) > 180 else base


@dataclass(frozen=True)
class PresignResult:
    url: str
    fields: Dict[str, str]
    key: str


def build_private_key(
    kind: str,
    *,
    company_id: str,
    filename: str,
    project_id: Optional[str] = None,
    bill_id: Optional[str] = None,
) -> str:
    """Build an S3 object key inside the private media location.

    NOTE: We intentionally include a UUID to avoid collisions.
    """

    safe = _safe_filename(filename)
    uid = uuid.uuid4().hex
    loc = (getattr(settings, "S3_PRIVATE_MEDIA_LOCATION", "private-media") or "private-media").strip("/")

    if kind == "expense_receipt":
        return f"{loc}/expense_receipts/{company_id}/{uid}_{safe}"
    if kind == "project_file":
        if not project_id:
            raise ValueError("project_id_required")
        return f"{loc}/projects/{company_id}/{project_id}/{uid}_{safe}"

    if kind == "bill_attachment":
        if not bill_id:
            raise ValueError("bill_id_required")
        return f"{loc}/bills/{company_id}/{bill_id}/{uid}_{safe}"

    raise ValueError("invalid_kind")


def _boto3_client():
    try:
        import boto3  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("boto3_not_installed") from e

    kwargs: Dict[str, Any] = {}
    region = getattr(settings, "AWS_S3_REGION_NAME", "") or None
    endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", "") or None
    if region:
        kwargs["region_name"] = region
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client(
        "s3",
        aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", "") or None,
        aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", "") or None,
        **kwargs,
    )


def presign_private_upload(*, key: str, filename: str, content_type: Optional[str] = None) -> PresignResult:
    """Generate a presigned POST for uploading to the PRIVATE bucket."""

    bucket = getattr(settings, "S3_PRIVATE_MEDIA_BUCKET", "") or getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
    if not bucket:
        raise RuntimeError("missing_private_bucket")

    expires = int(getattr(settings, "S3_PRESIGN_EXPIRE_SECONDS", 120) or 120)
    max_mb = int(getattr(settings, "S3_PRESIGN_MAX_SIZE_MB", 50) or 50)
    max_bytes = max_mb * 1024 * 1024

    ct = (content_type or "").strip()
    safe = _safe_filename(filename)

    fields: Dict[str, str] = {
        "acl": "private",
        "key": key,
        "Content-Disposition": f'attachment; filename="{safe}"',
    }
    conditions: list = [
        {"acl": "private"},
        {"key": key},
        ["content-length-range", 1, max_bytes],
    ]
    if ct:
        fields["Content-Type"] = ct
        conditions.append({"Content-Type": ct})

    client = _boto3_client()
    res = client.generate_presigned_post(
        Bucket=bucket,
        Key=key,
        Fields=fields,
        Conditions=conditions,
        ExpiresIn=expires,
    )

    return PresignResult(url=res["url"], fields=res["fields"], key=key)



def presign_private_download(*, key: str, filename: str | None = None, content_type: Optional[str] = None) -> str:
    """Generate a presigned GET URL for downloading from the PRIVATE bucket.

    We force an attachment disposition so browsers download with a friendly filename.
    """

    bucket = getattr(settings, "S3_PRIVATE_MEDIA_BUCKET", "") or getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
    if not bucket:
        raise RuntimeError("missing_private_bucket")

    expires = int(getattr(settings, "S3_PRESIGN_DOWNLOAD_EXPIRE_SECONDS", 120) or 120)

    safe = _safe_filename(filename or "file")
    params: Dict[str, Any] = {
        "Bucket": bucket,
        "Key": key,
        "ResponseContentDisposition": f'attachment; filename="{safe}"',
    }
    ct = (content_type or "").strip()
    if ct:
        params["ResponseContentType"] = ct

    client = _boto3_client()
    url = client.generate_presigned_url(
        ClientMethod="get_object",
        Params=params,
        ExpiresIn=expires,
    )
    return url


def presign_private_view(*, key: str, filename: str | None = None, content_type: Optional[str] = None) -> str:
    """Generate a presigned GET URL for *previewing* an object from the PRIVATE bucket.

    This uses an **inline** content disposition so browsers can render PDFs/images.
    For non-previewable types, callers should prefer presign_private_download().
    """

    bucket = getattr(settings, "S3_PRIVATE_MEDIA_BUCKET", "") or getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
    if not bucket:
        raise RuntimeError("missing_private_bucket")

    expires = int(getattr(settings, "S3_PRESIGN_DOWNLOAD_EXPIRE_SECONDS", 120) or 120)

    safe = _safe_filename(filename or "file")
    params: Dict[str, Any] = {
        "Bucket": bucket,
        "Key": key,
        "ResponseContentDisposition": f'inline; filename="{safe}"',
    }
    ct = (content_type or "").strip()
    if ct:
        params["ResponseContentType"] = ct

    client = _boto3_client()
    url = client.generate_presigned_url(
        ClientMethod="get_object",
        Params=params,
        ExpiresIn=expires,
    )
    return url


def delete_private_object(*, key: str) -> bool:
    """Best-effort delete of a private media object.

    Returns True if a delete call was issued, False if it was skipped due to config.

    We intentionally swallow S3 errors because deletes should not break core workflows.
    """
    key = (key or "").strip()
    if not key:
        return False

    if not getattr(settings, "USE_S3", False):
        return False
    if not getattr(settings, "S3_DELETE_ON_REMOVE", False):
        return False

    bucket = getattr(settings, "S3_PRIVATE_MEDIA_BUCKET", "") or getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
    if not bucket:
        return False

    try:
        client = _boto3_client()
        client.delete_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False
