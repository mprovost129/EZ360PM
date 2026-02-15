from __future__ import annotations

from urllib.parse import urlencode

from django import template


register = template.Library()


@register.simple_tag(takes_context=True)
def qs_replace(context, **kwargs) -> str:
    """Return the current querystring with keys replaced.

    Example:
        {% qs_replace page=2 %}
    """

    request = context.get("request")
    if request is None:
        return urlencode(kwargs)

    q = request.GET.copy()
    for k, v in kwargs.items():
        if v is None or v == "":
            q.pop(k, None)
        else:
            q[k] = str(v)
    encoded = q.urlencode()
    return encoded
