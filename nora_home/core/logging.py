"""
Structured logging.

Every log line carries the request id, the acting member, and the surface (web,
kiosk, wall, celery, mcp) so that "why did the wall display do that at 6am" is
answerable from logs/nora.log alone.

House apps: use `logging.getLogger(__name__)` and log normally. The context is
attached for you.
"""

from __future__ import annotations

import contextvars
import json
import logging
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("nora_request_id",
                                                                    default="-")
member_var: contextvars.ContextVar[str] = contextvars.ContextVar("nora_member", default="-")
surface_var: contextvars.ContextVar[str] = contextvars.ContextVar("nh_surface",
                                                                  default="server")

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message", "asctime", "request_id", "member", "surface", "taskName",
}


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.member = member_var.get()
        record.surface = surface_var.get()
        return True


class JSONFormatter(logging.Formatter):
    """One JSON object per line — greppable by hand, parseable by a script."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "member": getattr(record, "member", "-"),
            "surface": getattr(record, "surface", "server"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Anything passed as logger.info("...", extra={"item_id": 3}) rides along.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = repr(value)
        return json.dumps(payload, default=str)
