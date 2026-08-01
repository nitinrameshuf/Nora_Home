"""
HTTP transport for the house MCP tools.

Two endpoints, both authenticated with a bearer token equal to NORA_HOME_MCP_TOKEN:

    GET  /mcp/tools/          → the tool list an agent can choose from
    POST /mcp/call/           → {"name": "...", "arguments": {...}}

This is deliberately a thin JSON surface rather than a full MCP transport: it is what
lets a phone shortcut, the robot, or a remote agent reach the house over the LAN. For
a local stdio MCP client (Claude Desktop, Claude Code), use `manage.py mcp_stdio`.
"""

from __future__ import annotations

import hmac
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from nora_home.core.audit import record
from nora_home.mcpserver.registry import all_tools, get_tool

logger = logging.getLogger(__name__)


def _authorized(request) -> tuple[bool, list[str]]:
    """Returns (ok, scopes). A device token's scopes win over the shared secret."""
    if not settings.NORA_HOME_MCP_ENABLED:
        return False, []

    header = request.headers.get("Authorization", "")
    presented = header[7:].strip() if header.startswith("Bearer ") else ""
    if not presented:
        return False, []

    # A registered device token — preferred, because it is revocable and scoped.
    from nora_home.core.api.auth import hash_token
    from nora_home.core.models import DeviceToken

    if presented.startswith("nora_"):
        parts = presented.split("_", 2)
        if len(parts) == 3:
            digest = hash_token(presented)
            for token in DeviceToken.objects.filter(prefix=parts[1],
                                                    revoked_at__isnull=True):
                if hmac.compare_digest(token.token_hash, digest):
                    return True, list(token.scopes or ["read"])
        return False, []

    # The shared secret from .env — read-only, for bootstrapping.
    if settings.NORA_HOME_MCP_TOKEN and hmac.compare_digest(presented,
                                                       settings.NORA_HOME_MCP_TOKEN):
        return True, ["read"]
    return False, []


@require_GET
def list_tools(request):
    ok, scopes = _authorized(request)
    if not ok:
        return JsonResponse({"error": "unauthorized"}, status=401)

    granted = set(scopes)
    return JsonResponse({
        "house": settings.NORA_HOME_NAME,
        "scopes": scopes,
        "tools": [
            tool.as_definition() for tool in all_tools()
            if granted.issuperset(set(tool.scopes))
        ],
    })


@csrf_exempt
@require_POST
def call_tool(request):
    ok, scopes = _authorized(request)
    if not ok:
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "body must be JSON"}, status=400)

    name = payload.get("name", "")
    arguments = payload.get("arguments") or {}
    if not isinstance(arguments, dict):
        return JsonResponse({"error": "arguments must be an object"}, status=400)

    tool = get_tool(name)
    if tool is None:
        return JsonResponse({"error": f"no such tool: {name}"}, status=404)

    if not set(scopes).issuperset(set(tool.scopes)):
        record("mcp", "tool.denied", subject=name, severity="warning", source="mcp",
               required=tool.scopes, granted=scopes)
        return JsonResponse({"error": "this token lacks the scope for that tool"},
                            status=403)

    try:
        result = tool.call(arguments)
    except TypeError as exc:
        return JsonResponse({"error": f"bad arguments: {exc}"}, status=400)
    except Exception:
        logger.exception("MCP tool %s failed", name)
        return JsonResponse({"error": "the tool raised an error"}, status=500)

    record("mcp", "tool.called", subject=name, source="mcp",
           dangerous=tool.dangerous, arguments=list(arguments))
    return JsonResponse({"name": name, "result": result}, safe=False,
                        json_dumps_params={"default": str})
