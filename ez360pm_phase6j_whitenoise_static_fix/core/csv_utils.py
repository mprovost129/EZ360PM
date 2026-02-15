from __future__ import annotations

import csv
from typing import Iterable, Sequence

from django.http import HttpResponse


def csv_response(filename: str, header: Sequence[str], rows: Iterable[Sequence[object]]) -> HttpResponse:
    """Return a streaming-ish CSV response (small/medium reports)."""
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(resp)
    writer.writerow(list(header))
    for r in rows:
        writer.writerow(list(r))
    return resp
