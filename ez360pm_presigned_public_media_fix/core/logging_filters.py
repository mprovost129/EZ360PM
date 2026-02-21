from __future__ import annotations

import logging

from core.request_context import get_request_id


class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # default blank if not on request context
        rid = getattr(record, "request_id", "") or get_request_id()
        record.request_id = rid or ""
        return True
