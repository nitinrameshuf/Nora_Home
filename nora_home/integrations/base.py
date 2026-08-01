"""
The integration framework.

An integration is anything that pulls the outside world in on a schedule: Home
Assistant entity states, a stock portfolio, weather, a calendar, a delivery tracker.
The platform owns scheduling, retries, failure alerting, and credential storage, so
an integration only has to implement `fetch()`.

    from nora_home.integrations.base import Integration, register

    @register
    class HomeAssistant(Integration):
        slug = "home_assistant"
        name = "Home Assistant"
        default_interval_minutes = 5
        config_fields = {
            "base_url": "http://homeassistant.local:8123",
            "entities": ["sensor.living_room_temperature"],
        }
        secret_fields = ["token"]

        def fetch(self):
            data = self.get(f"{self.config['base_url']}/api/states",
                            headers={"Authorization": f"Bearer {self.secret('token')}"})
            for entity in data:
                if entity["entity_id"] in self.config["entities"]:
                    self.record(entity["entity_id"], float(entity["state"]))
            return {"entities": len(self.config["entities"])}

Raise `IntegrationError` for an expected failure (service down, bad credentials);
anything else is treated as a bug and logged with a traceback.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, type["Integration"]] = {}

DEFAULT_TIMEOUT = 15


class IntegrationError(Exception):
    """An expected failure. The platform records it and retries on schedule."""


class Integration:
    """Subclass this, set the class attributes, implement `fetch()`."""

    slug: str = ""
    name: str = ""
    description: str = ""
    icon: str = "link"
    default_interval_minutes: int = 15

    # Shape of the editable config, with defaults. Stored on the model as JSON.
    config_fields: dict[str, Any] = {}
    # Names of credentials. Values live in the environment as
    # NORA_HOME_INTEGRATION_<SLUG>_<FIELD>, never in the database.
    secret_fields: list[str] = []

    def __init__(self, record):
        self.record_model = record
        self.config = {**self.config_fields, **(record.config or {})}

    # ── to implement ───────────────────────────────────────────────────────────
    def fetch(self) -> dict:
        """Pull fresh data. Return a small summary dict for the run log."""
        raise NotImplementedError

    def check(self) -> bool:
        """Optional cheap connectivity test, used by the 'Test' button."""
        return True

    # ── helpers ────────────────────────────────────────────────────────────────
    def get(self, url: str, **kwargs):
        """HTTP GET with a timeout and a useful error. Never hangs a worker."""
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        try:
            response = requests.get(url, **kwargs)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise IntegrationError(f"GET {url} failed: {exc}") from exc
        return response.json()

    def post(self, url: str, **kwargs):
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        try:
            response = requests.post(url, **kwargs)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise IntegrationError(f"POST {url} failed: {exc}") from exc
        return response.json() if response.content else {}

    def secret(self, field: str) -> str:
        """Read a credential from the environment. Secrets never touch the DB."""
        import os

        key = f"NORA_HOME_INTEGRATION_{self.slug.upper()}_{field.upper()}"
        value = os.environ.get(key, "")
        if not value:
            raise IntegrationError(f"Missing credential: set {key} in .env")
        return value

    def record(self, series_key: str, value: float, **tags):
        """Store a measurement. Namespaced under the integration automatically."""
        from nora_home.telemetry.api import record_reading

        return record_reading(f"{self.slug}.{series_key}", value,
                              source="integration", app_slug="integrations", **tags)

    def store_document(self, name: str, document: dict):
        """Keep a raw payload in Mongo — useful when the shape is not yet known."""
        from nora_home.datastores.mongo import MongoUnavailable, put_document

        try:
            put_document(name, document, app_slug=f"integration.{self.slug}")
        except MongoUnavailable as exc:
            logger.debug("Skipped storing %s payload: %s", self.slug, exc)

    def alert(self, title: str, body: str = "", severity: str = "warning"):
        from nora_home.notifications.api import notify_house

        notify_house(title=title, body=body, severity=severity,
                     app_slug="integrations", dedupe_key=f"integration:{self.slug}")


def register(cls: type[Integration]) -> type[Integration]:
    if not cls.slug:
        raise ValueError(f"{cls.__name__} must define a slug")
    _REGISTRY[cls.slug] = cls
    return cls


def available() -> dict[str, type[Integration]]:
    return dict(_REGISTRY)


def get_class(slug: str) -> type[Integration] | None:
    return _REGISTRY.get(slug)
