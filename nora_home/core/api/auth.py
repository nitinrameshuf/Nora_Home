"""
Device token authentication for non-browser clients.

The wall display, the kiosk, the Nora robot, and phone shortcuts authenticate with

    Authorization: Bearer nora_<prefix>_<secret>

Tokens are stored hashed; the plaintext is shown once at creation time by
`manage.py issue_device_token`.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from django.utils import timezone
from rest_framework import authentication, exceptions

from nora_home.core.models import DeviceToken

TOKEN_PREFIX = "nora"


def generate_token() -> tuple[str, str, str]:
    """Return (plaintext, prefix, hash). Plaintext is never stored."""
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    plaintext = f"{TOKEN_PREFIX}_{prefix}_{secret}"
    return plaintext, prefix, hash_token(plaintext)


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


class DeviceTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(self.keyword + " "):
            return None

        plaintext = header[len(self.keyword) + 1:].strip()
        if not plaintext.startswith(TOKEN_PREFIX + "_"):
            return None

        parts = plaintext.split("_", 2)
        if len(parts) != 3:
            raise exceptions.AuthenticationFailed("Malformed device token.")

        candidates = DeviceToken.objects.filter(prefix=parts[1], revoked_at__isnull=True)
        digest = hash_token(plaintext)
        for token in candidates:
            if hmac.compare_digest(token.token_hash, digest):
                DeviceToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
                if token.member is None:
                    raise exceptions.AuthenticationFailed(
                        "Device token is not bound to a house member."
                    )
                request.device_token = token
                return (token.member, token)

        raise exceptions.AuthenticationFailed("Invalid or revoked device token.")

    def authenticate_header(self, request):  # noqa: ARG002
        return self.keyword
