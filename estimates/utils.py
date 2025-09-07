# estimates/utils.py
from __future__ import annotations

from django.utils import timezone

from company.models import Company
from .models import Estimate


def generate_estimate_number(company: Company) -> str:
    """
    Format: EST-YYYYMM-#### (per company, per month).
    """
    prefix = timezone.now().strftime("EST-%Y%m")
    last = (
        Estimate.objects
        .filter(company=company, number__startswith=prefix)
        .order_by("number")
        .last()
    )
    if not last:
        seq = 1
    else:
        try:
            seq = int(str(last.number).split("-")[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}-{seq:04d}"
