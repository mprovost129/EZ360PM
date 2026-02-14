from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def get_item(d: dict, key):
    try:
        return d.get(str(key))
    except Exception:
        return None
