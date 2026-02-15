from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class PresignedPost:
    url: str
    fields: dict
    object_name: str  # storage-relative name (without storage.location prefix)
    full_key: str  # full S3 object key including storage.location
    expires_in: int


def _safe_filename(filename: str) -> str:
    name = os.path.basename(filename or "")
    name = name.replace("\\", "_").replace("/", "_")
    name = name.strip() or "file"
    # Avoid absurd keys
    return name[:180]


def _require_s3_enabled() -> None:
    if not getattr(settings, "USE_S3", False):
        raise RuntimeError("S3 is not enabled (USE_S3=0).")

    # We rely on boto3 being available via django-storages[boto3]
    try:
        import boto3  # noqa: F401
        from botocore.config import Config  # noqa: F401
    except Exception as e:  # pragma: no cover
        raise RuntimeError("boto3 is not installed. Install django-storages[boto3].") from e


def presign_private_upload_expense_receipt(*, company_id: str, filename: str, content_type: str) -> PresignedPost:
    """Create a presigned POST for uploading an expense receipt directly to the *private* media bucket."""

    _require_s3_enabled()
    object_name = f"expense_receipts/{company_id}/{uuid.uuid4().hex}_{_safe_filename(filename)}"
    return _presign_private_post(object_name=object_name, content_type=content_type)


def presign_private_upload_project_file(*, company_id: str, project_id: str, filename: str, content_type: str) -> PresignedPost:
    """Create a presigned POST for uploading a project file directly to the *private* media bucket."""

    _require_s3_enabled()
    object_name = f"projects/{company_id}/{project_id}/{uuid.uuid4().hex}_{_safe_filename(filename)}"
    return _presign_private_post(object_name=object_name, content_type=content_type)


def _presign_private_post(*, object_name: str, content_type: str) -> PresignedPost:
    import boto3
    from botocore.config import Config

    bucket = getattr(settings, "S3_PRIVATE_MEDIA_BUCKET", "") or getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
    if not bucket:
        raise RuntimeError("S3 private bucket is not configured (S3_PRIVATE_MEDIA_BUCKET/AWS_STORAGE_BUCKET_NAME).")

    location = (getattr(settings, "S3_PRIVATE_MEDIA_LOCATION", "private-media") or "private-media").strip("/")
    full_key = f"{location}/{object_name.lstrip('/')}"

    expires_in = int(getattr(settings, "S3_PRESIGN_POST_EXPIRE_SECONDS", 300) or 300)

    endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", "") or None
    region_name = getattr(settings, "AWS_S3_REGION_NAME", "") or None
    sigver = getattr(settings, "AWS_S3_SIGNATURE_VERSION", "s3v4") or "s3v4"

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region_name,
        config=Config(signature_version=sigver),
    )

    fields = {
        "Content-Type": content_type or "application/octet-stream",
    }

    conditions = [
        {"Content-Type": fields["Content-Type"]},
        ["content-length-range", 1, 1024 * 1024 * 200],  # 200MB default guardrail
    ]

    post = client.generate_presigned_post(
        Bucket=bucket,
        Key=full_key,
        Fields=fields,
        Conditions=conditions,
        ExpiresIn=expires_in,
    )

    return PresignedPost(url=post["url"], fields=post["fields"], object_name=object_name, full_key=full_key, expires_in=expires_in)
