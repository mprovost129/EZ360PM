from __future__ import annotations

import logging

from .request_context import get_request_id


class RequestIDLogFilter(logging.Filter):
    """Inject request_id into log records for correlation."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = get_request_id() or "-"
        setattr(record, "request_id", rid)
        return True
