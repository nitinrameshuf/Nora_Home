"""
Health checks for every dependency the house relies on.

Each probe is isolated and time-bounded: a dead Mongo must report "mongo: down",
not hang the health endpoint that systemd is watching.
"""

from __future__ import annotations

import logging
import shutil
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.db import connections

logger = logging.getLogger(__name__)

PROBE_TIMEOUT = 2.0


def _tcp_ok(host: str, port: int, timeout: float = PROBE_TIMEOUT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _from_url(url: str, default_port: int) -> tuple[str, int]:
    parsed = urlparse(url)
    return parsed.hostname or "127.0.0.1", parsed.port or default_port


def check_database() -> dict:
    started = time.monotonic()
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "ok", "ms": round((time.monotonic() - started) * 1000, 1)}
    except Exception as exc:
        return {"status": "down", "error": str(exc)[:200]}


def check_redis() -> dict:
    host, port = _from_url(settings.NORA_HOME_REDIS_URL, 6379)
    return {"status": "ok" if _tcp_ok(host, port) else "down", "host": f"{host}:{port}"}


def check_rabbitmq() -> dict:
    url = settings.CELERY_BROKER_URL
    if url.startswith(("memory://", "redis://")):
        return {"status": "skipped", "reason": "broker is not rabbitmq"}
    host, port = _from_url(url, 5672)
    return {"status": "ok" if _tcp_ok(host, port) else "down", "host": f"{host}:{port}"}


def check_mongo() -> dict:
    if not settings.NORA_HOME_MONGO_ENABLED:
        return {"status": "skipped"}
    host, port = _from_url(settings.NORA_HOME_MONGO_URI, 27017)
    return {"status": "ok" if _tcp_ok(host, port) else "down", "host": f"{host}:{port}"}


def check_object_storage() -> dict:
    if not settings.NORA_HOME_S3_ENABLED:
        return {"status": "skipped", "reason": "local filesystem storage"}
    host, port = _from_url(settings.NORA_HOME_S3_ENDPOINT_URL, 9000)
    return {"status": "ok" if _tcp_ok(host, port) else "down", "host": f"{host}:{port}"}


def check_disk() -> dict:
    try:
        usage = shutil.disk_usage(settings.BASE_DIR)
        percent = usage.used / usage.total * 100
        return {
            "status": "ok" if percent < 90 else "warning",
            "percent_used": round(percent, 1),
            "free_gb": round(usage.free / 1024**3, 1),
        }
    except Exception as exc:
        return {"status": "unknown", "error": str(exc)[:200]}


def check_cpu_temperature() -> dict:
    """Raspberry Pi thermal zone. Silently 'unknown' anywhere else."""
    path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        celsius = int(path.read_text().strip()) / 1000
    except (OSError, ValueError):
        return {"status": "unknown"}
    status = "ok" if celsius < 70 else ("warning" if celsius < 80 else "critical")
    return {"status": status, "celsius": round(celsius, 1)}


PROBES = {
    "database": check_database,
    "redis": check_redis,
    "rabbitmq": check_rabbitmq,
    "mongo": check_mongo,
    "object_storage": check_object_storage,
    "disk": check_disk,
    "cpu_temperature": check_cpu_temperature,
}

# A house that cannot reach Mongo is degraded; one that cannot reach MySQL is down.
CRITICAL = {"database", "disk"}


def collect_health() -> dict:
    services = {}
    for name, probe in PROBES.items():
        try:
            services[name] = probe()
        except Exception as exc:
            logger.exception("Health probe %s blew up", name)
            services[name] = {"status": "down", "error": str(exc)[:200]}

    degraded = [k for k, v in services.items() if v.get("status") in {"down", "critical"}]
    healthy = not any(name in CRITICAL for name in degraded)

    return {
        "healthy": healthy,
        "degraded": degraded,
        "house": settings.NORA_HOME_NAME,
        "version": settings.NORA_HOME_VERSION,
        "environment": settings.NORA_HOME_ENV,
        "services": services,
    }
