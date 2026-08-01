"""
Websocket routes for the whole platform.

House apps can add their own by exporting `websocket_urlpatterns` from a
`routing.py` in their package; it is picked up automatically.
"""

from __future__ import annotations

import logging
from importlib import import_module

from django.urls import path

from nora_home.core.registry import registered_apps
from nora_home.displays.consumers import DisplayConsumer, KioskConsumer
from nora_home.ui.consumers import HomeBotConsumer

logger = logging.getLogger(__name__)

websocket_urlpatterns = [
    # The always-on 24" display subscribes here and is driven by the kiosk/celery.
    path("ws/display/<slug:slug>/", DisplayConsumer.as_asgi()),
    # The 10.1" kiosk: sends commands, receives acknowledgements.
    path("ws/kiosk/", KioskConsumer.as_asgi()),
    # The home bot: nudges, reactions, and live notification pushes to any browser.
    path("ws/homebot/", HomeBotConsumer.as_asgi()),
]


def _collect_house_app_routes():
    for meta in registered_apps():
        if meta.is_platform:
            continue
        try:
            module = import_module(f"{meta.module}.routing")
        except ModuleNotFoundError:
            continue
        except Exception:
            logger.exception("House app %s has a broken routing.py", meta.slug)
            continue
        websocket_urlpatterns.extend(getattr(module, "websocket_urlpatterns", []))


_collect_house_app_routes()
