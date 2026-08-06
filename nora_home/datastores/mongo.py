"""
MongoDB access for house apps.

MySQL holds anything relational and anything the task and escalation engines need
to join across. Mongo holds the rest: journals, AI transcripts, raw integration
payloads, sensor bursts, notes — documents whose shape you do not want to migrate
every time an idea changes.

    from nora_home.datastores.mongo import collection

    journal = collection("journal", app_slug="selfimprove")
    journal.insert_one({"member": "nitin", "text": "...", "mood": 7})

Collections are namespaced per app (`selfimprove.journal`), so two apps cannot
collide on a name. The client is created once and shared; pymongo pools connections.
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_client = None
_lock = threading.Lock()


class MongoUnavailable(Exception):
    """Mongo is disabled or unreachable. Catch it; the house should still work."""


def get_client():
    """The shared MongoClient. Import of pymongo is deferred so the platform runs
    without Mongo installed at all."""
    global _client
    if not settings.NORA_HOME_MONGO_ENABLED:
        raise MongoUnavailable("Mongo is disabled (NORA_HOME_MONGO_ENABLED=0).")

    if _client is None:
        with _lock:
            if _client is None:
                try:
                    from pymongo import MongoClient
                except ImportError as exc:
                    raise MongoUnavailable("pymongo is not installed.") from exc
                _client = MongoClient(
                    settings.NORA_HOME_MONGO_URI,
                    serverSelectionTimeoutMS=3000,
                    connectTimeoutMS=3000,
                    tz_aware=True,
                    appname="nora-home",
                )
    return _client


def get_database():
    return get_client()[settings.NORA_HOME_MONGO_DB]


def collection(name: str, *, app_slug: str = "core"):
    """A namespaced collection handle: collection("journal", app_slug="x") → x.journal."""
    return get_database()[f"{app_slug}.{name}"]


def put_document(name: str, document: dict, *, app_slug: str = "core"):
    """Insert with house metadata attached, so every document is traceable later."""
    payload = {**document, "_app": app_slug, "_created_at": timezone.now()}
    return collection(name, app_slug=app_slug).insert_one(payload)


def ping() -> bool:
    try:
        get_client().admin.command("ping")
        return True
    except Exception as exc:
        logger.warning("Mongo ping failed: %s", exc)
        return False


def ensure_indexes(name: str, indexes: list, *, app_slug: str = "core"):
    """Idempotent index creation. Call it from your AppConfig.ready().

        ensure_indexes("journal", [[("member", 1), ("_created_at", -1)]],
                       app_slug="selfimprove")
    """
    try:
        target = collection(name, app_slug=app_slug)
        for index in indexes:
            target.create_index(index)
    except Exception:
        logger.exception("Could not create Mongo indexes for %s.%s", app_slug, name)
