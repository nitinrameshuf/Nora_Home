"""Audit trail helper. Use for anything a family member might later ask about."""

from __future__ import annotations

import logging

from nora_home.core.logging import surface_var
from nora_home.core.models import AuditEvent

logger = logging.getLogger(__name__)


def record(app_slug: str, action: str, *, actor=None, subject: str = "",
           severity: str = AuditEvent.Severity.INFO, source: str = "",
           **detail) -> AuditEvent | None:
    """Write an audit row. Never raises — auditing must not break the caller.

        record("workout", "session.logged", actor=request.user,
               subject="Push day", sets=18)
    """
    try:
        event = AuditEvent.objects.create(
            actor=actor if getattr(actor, "pk", None) else None,
            app_slug=app_slug,
            action=action,
            severity=severity,
            subject=subject[:255],
            detail=detail,
            source=source or surface_var.get(),
        )
    except Exception:
        logger.exception("Failed to write audit event %s:%s", app_slug, action)
        return None
    logger.info("audit %s:%s", app_slug, action,
                extra={"app_slug": app_slug, "action": action, "subject": subject})
    return event
