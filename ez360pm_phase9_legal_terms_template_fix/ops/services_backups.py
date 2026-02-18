from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from django.conf import settings


class BackupUploadError(RuntimeError):
    pass


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def s3_backup_key(filename: str) -> str:
    prefix = (getattr(settings, "BACKUP_S3_PREFIX", "") or "").strip().strip("/")
    if not prefix:
        prefix = "ez360pm/backups/db"
    return f"{prefix}/{filename}"


def upload_backup_to_s3(local_path: Path, *, key: str | None = None) -> dict[str, Any]:
    """Upload a backup file to S3.

    Requires:
      - BACKUP_S3_BUCKET
      - AWS creds/region via environment (same as other S3 uses)

    Returns metadata dict safe to store in BackupRun.details.
    """

    bucket = (getattr(settings, "BACKUP_S3_BUCKET", "") or "").strip()
    if not bucket:
        raise BackupUploadError("BACKUP_S3_BUCKET is not set")

    try:
        import boto3  # type: ignore
    except Exception as e:  # pragma: no cover
        raise BackupUploadError("boto3 is required for BACKUP_STORAGE=s3") from e

    if not local_path.exists() or not local_path.is_file():
        raise BackupUploadError(f"Backup file not found: {local_path}")

    key_final = key or s3_backup_key(local_path.name)

    s3 = boto3.client("s3")
    extra_args: dict[str, Any] = {
        "ContentType": "application/gzip" if local_path.name.endswith(".gz") else "text/plain",
        "ServerSideEncryption": "AES256",
    }

    s3.upload_file(str(local_path), bucket, key_final, ExtraArgs=extra_args)

    return {
        "bucket": bucket,
        "key": key_final,
        "size_bytes": int(local_path.stat().st_size),
        "sha256": sha256_file(local_path),
    }
