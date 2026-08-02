"""
Raspberry Pi 5 (8GB) — the real deployment.

Differences from prod: the Pi lives on the house LAN behind no TLS terminator by
default, and resources are finite, so worker counts and connection pools are small.
"""

from .prod import *  # noqa: F403
from .base import env_int, env_list

# Django's ALLOWED_HOSTS has no CIDR/subnet syntax — a bare "192.168.1.0/24" here
# (an earlier version of this file) never matched anything, so every request that
# didn't say exactly "localhost" or "127.0.0.1" got a 400, including every phone
# and laptop on the house LAN. "*" is correct for this specific case: the LAN is
# already the trust boundary everywhere else in this house (see CLAUDE.md §4).
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["*"])

# Four cores, and the always-on display holds a websocket permanently.
CELERY_WORKER_CONCURRENCY = env_int("NORA_HOME_CELERY_CONCURRENCY", 3)
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 200_000  # KB — recycle before the Pi swaps

DATABASES["default"]["CONN_MAX_AGE"] = 300  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405

# The wall display never logs out.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365
