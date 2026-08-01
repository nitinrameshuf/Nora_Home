"""Attach a request id and acting member to every log line and response."""

from __future__ import annotations

import time
import uuid

from nora_home.core.logging import member_var, request_id_var, surface_var


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.request_id = request_id
        token_rid = request_id_var.set(request_id)

        user = getattr(request, "user", None)
        member = getattr(user, "username", "-") if user and user.is_authenticated else "-"
        token_member = member_var.set(member)
        token_surface = surface_var.set(getattr(request, "nh_surface", "web"))

        started = time.monotonic()
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token_rid)
            member_var.reset(token_member)
            surface_var.reset(token_surface)

        response["X-Request-ID"] = request_id
        response["X-Nora-Duration-ms"] = f"{(time.monotonic() - started) * 1000:.0f}"
        return response
