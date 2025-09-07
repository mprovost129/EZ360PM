# company/context_processors.py
from __future__ import annotations

from typing import Any, Mapping
from django.http import HttpRequest

from .utils import get_active_company

__all__ = ["active_company"]


def active_company(request: HttpRequest) -> Mapping[str, Any]:
    """
    Template context processor.

    Injects the current active company for the request into all templates.
    This is lightweight—if you need richer context (members, role, etc.),
    prefer a dedicated view helper instead of bloating every template.
    """
    try:
        return {"active_company": get_active_company(request)}
    except Exception:
        # Never break rendering due to company lookup issues
        return {"active_company": None}
