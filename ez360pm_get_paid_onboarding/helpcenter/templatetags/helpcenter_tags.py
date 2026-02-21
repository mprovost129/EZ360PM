# helpcenter/templatetags/helpcenter_tags.py
from __future__ import annotations

from django import template
from django.templatetags.static import static

from helpcenter.models import HelpCenterScreenshot

register = template.Library()


@register.simple_tag
def hc_screenshot(key: str, default_static_path: str = "") -> str:
    """
    Return an uploaded helpcenter screenshot URL by key.
    Falls back to a static placeholder path if no upload exists.

    Usage:
      <img src="{% hc_screenshot 'accounting_overview' 'images/helpcenter/accounting_overview.png' %}">
    """
    key = (key or "").strip()
    if not key:
        return static(default_static_path) if default_static_path else ""

    obj = HelpCenterScreenshot.objects.filter(key=key).first()
    if obj and getattr(obj, "image", None):
        try:
            return obj.image.url
        except Exception:
            pass

    return static(default_static_path) if default_static_path else ""
