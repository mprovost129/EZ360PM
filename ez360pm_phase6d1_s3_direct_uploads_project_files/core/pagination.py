from __future__ import annotations

from dataclasses import dataclass

from django.core.paginator import EmptyPage, Page, Paginator
from django.http import HttpRequest


@dataclass(frozen=True)
class PaginationResult:
    paginator: Paginator
    page_obj: Page
    object_list: list
    per_page: int


def _coerce_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def paginate(
    request: HttpRequest,
    qs,
    *,
    default_per_page: int = 25,
    max_per_page: int = 200,
    page_param: str = "page",
    per_page_param: str = "per_page",
) -> PaginationResult:
    """Standard pagination helper.

    - Supports ?page= and ?per_page=
    - Clamps per_page to max_per_page
    - Returns a stable PaginationResult used by templates.
    """

    per_page = _coerce_int(request.GET.get(per_page_param), default_per_page)
    if per_page <= 0:
        per_page = default_per_page
    per_page = min(per_page, max_per_page)

    page_number = _coerce_int(request.GET.get(page_param), 1)
    if page_number <= 0:
        page_number = 1

    paginator = Paginator(qs, per_page)
    try:
        page_obj = paginator.page(page_number)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    return PaginationResult(
        paginator=paginator,
        page_obj=page_obj,
        object_list=list(page_obj.object_list),
        per_page=per_page,
    )
