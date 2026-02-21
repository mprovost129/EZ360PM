from __future__ import annotations

import mimetypes
import os
from typing import Optional, Tuple, Union

from django.conf import settings
from django.core.files.storage import Storage
from django.core.files.base import File
from django.db.models.fields.files import FieldFile

from core.s3_presign import presign_private_download, presign_private_view


PREVIEWABLE_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _normalize_key(*, storage: Optional[Storage], name: str) -> str:
    """Normalize a storage-relative name to a full S3 key including storage.location when applicable."""
    key = (name or "").lstrip("/")
    if not key:
        return ""

    loc = getattr(storage, "location", "") if storage is not None else ""
    loc = (loc or "").strip("/")
    if loc and not key.startswith(loc + "/"):
        key = f"{loc}/{key}"
    return key


def guess_content_type(filename: str, fallback: str = "application/octet-stream") -> str:
    ct, _ = mimetypes.guess_type(filename or "")
    return ct or fallback


def is_previewable(filename: str, content_type: str = "") -> bool:
    ext = os.path.splitext((filename or "").lower())[1]
    if ext in PREVIEWABLE_EXTS:
        return True
    ct = (content_type or "").lower()
    return ct.startswith("image/") or ct == "application/pdf"


def build_private_access_url(
    *,
    file_or_key: Union[FieldFile, str],
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
    preview: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """Return (url, error_code) for accessing a private object.

    - For S3: returns a presigned URL (attachment by default, inline when preview=True and previewable)
    - For local dev: returns the FieldFile.url when a FieldFile is provided.
      For string keys in local mode, returns (None, "local_key_not_supported").

    NOTE: This helper does *not* enforce authorization; callers must enforce access controls.
    """

    # FieldFile path
    if hasattr(file_or_key, "name") and not isinstance(file_or_key, str):
        ff: FieldFile = file_or_key
        if not ff:
            return None, "missing_file"
        effective_filename = filename or os.path.basename(ff.name) or "file"
        effective_ct = content_type or guess_content_type(effective_filename)

        if not getattr(settings, "USE_S3", False):
            # Local dev: let Django/static serve it (MEDIA_URL)
            try:
                return ff.url, None
            except Exception:
                return None, "local_url_failed"

        # S3: build key and presign
        key = _normalize_key(storage=getattr(ff, "storage", None), name=ff.name)
        if not key:
            return None, "missing_key"

        do_preview = bool(preview and is_previewable(effective_filename, effective_ct))
        try:
            if do_preview:
                return presign_private_view(key=key, filename=effective_filename, content_type=effective_ct), None
            return presign_private_download(key=key, filename=effective_filename, content_type=effective_ct), None
        except Exception:
            return None, "presign_failed"

    # String key path (used by BillAttachment)
    key = (str(file_or_key) or "").strip()
    if not key:
        return None, "missing_key"

    effective_filename = filename or os.path.basename(key) or "file"
    effective_ct = content_type or guess_content_type(effective_filename)

    if not getattr(settings, "USE_S3", False):
        return None, "local_key_not_supported"

    do_preview = bool(preview and is_previewable(effective_filename, effective_ct))
    try:
        if do_preview:
            return presign_private_view(key=key, filename=effective_filename, content_type=effective_ct), None
        return presign_private_download(key=key, filename=effective_filename, content_type=effective_ct), None
    except Exception:
        return None, "presign_failed"
