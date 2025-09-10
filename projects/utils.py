# projects/utils.py
from __future__ import annotations

from datetime import timezone
from typing import TYPE_CHECKING, Iterable, Optional

from company.models import Company
from projects.models import Project


if TYPE_CHECKING:  # for type hints only; avoids runtime import cycles
    from company.models import Company


def _max_suffix_for_prefix(values: Iterable[str], prefix: str) -> int:
    max_n = 0
    plen = len(prefix)
    for raw in values:
        s = (str(raw) or "").strip()
        if not s.startswith(prefix):
            continue
        tail = s[plen:]
        if tail.isdigit():
            try:
                n = int(tail)
                if n > max_n:
                    max_n = n
            except Exception:
                pass
    return max_n

def generate_project_number(
    company: "Company",
    *,
    seq_width: int = 2,
    width: Optional[int] = None,  # legacy kwarg support
) -> str:
    if width is not None:
        seq_width = int(width)

    # Current local date -> YYMM prefix
    try:
        today = timezone.localdate()          # type: ignore # Django util
    except Exception:
        from datetime import date             # fallback if needed
        today = date.today()
    prefix = today.strftime("%y%m")

    existing = (
        Project.objects.filter(company=company, number__startswith=prefix)
        .exclude(number__isnull=True)
        .exclude(number__exact="")
        .values_list("number", flat=True)
    )

    start = _max_suffix_for_prefix(existing, prefix)
    n = start + 1

    while True:
        candidate = f"{prefix}{n:0{seq_width}d}"  # e.g., 250901
        if not Project.objects.filter(company=company, number__iexact=candidate).exists():
            return candidate
        n += 1