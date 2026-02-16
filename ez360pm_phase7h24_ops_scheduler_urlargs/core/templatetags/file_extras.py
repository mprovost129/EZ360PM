from __future__ import annotations

from django import template

from core.services.private_media import is_previewable


register = template.Library()


@register.filter
def previewable(filename: str) -> bool:
    """Return True if filename/content-type is generally previewable in-browser (PDF/images)."""
    return is_previewable(filename or "", "")
