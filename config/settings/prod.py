"""Hardened settings. config.settings.pi imports this and relaxes what a LAN needs."""

from .base import *  # noqa: F403
from .base import env

DEBUG = False

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # the Nora bot posts via fetch() with the CSRF token
SESSION_COOKIE_SAMESITE = "Lax"

# Only meaningful once TLS terminates in front of us.
SECURE_SSL_REDIRECT = env("NORA_HOME_FORCE_HTTPS", "0") == "1"
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
SECURE_HSTS_SECONDS = 31536000 if SECURE_SSL_REDIRECT else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_SSL_REDIRECT
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if env("SENTRY_DSN"):
    import sentry_sdk

    sentry_sdk.init(dsn=env("SENTRY_DSN"), traces_sample_rate=0.05, send_default_pii=False)
