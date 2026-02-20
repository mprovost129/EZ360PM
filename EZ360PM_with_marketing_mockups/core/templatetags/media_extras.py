from __future__ import annotations

from django import template

register = template.Library()


@register.filter(name="safe_media_url")
def safe_media_url(field_file) -> str:
    """Return a safe URL for a FieldFile/ImageFieldFile.

    Some storages (e.g., S3 via boto3) can raise during url resolution if the
    storage backend is misconfigured in the current environment. Templates should
    never 500 because a logo URL can't be resolved.
    """
    if not field_file:
        return ""
    try:
        return str(field_file.url)
    except Exception:
        return ""
