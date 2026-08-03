"""
Websocket consumers for the two screens.

DisplayConsumer  — the wall display connects and listens. It sends heartbeats so the
                   house knows the screen is alive, and receives show/banner/refresh.
KioskConsumer    — the 10.1" touchscreen connects and *sends*. Its commands are
                   validated here and relayed onto the wall's group.

Authentication is session-based: both screens run a logged-in kiosk browser on the
Pi itself. An unauthenticated socket is closed rather than served, so a laptop on the
guest network cannot take over the living-room screen.
"""

from __future__ import annotations

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from nora_home.displays.bus import ALL_DISPLAYS_GROUP, group_for

logger = logging.getLogger(__name__)

# Commands the kiosk is allowed to issue. Anything else is ignored and logged.
# "navigate" sends the wall to a page of the real app (path rides along in the
# payload unparsed — see KioskConsumer.receive_json) rather than switching
# between pre-rendered ambient panels like the others in this set.
KIOSK_ACTIONS = {"show", "pin", "unpin", "next", "previous", "refresh",
                 "brightness", "sleep", "wake", "say", "navigate"}


class DisplayConsumer(AsyncJsonWebsocketConsumer):
    """The receiving end: a screen that shows things."""

    async def connect(self):
        self.slug = self.scope["url_route"]["kwargs"]["slug"]
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.group = group_for(self.slug)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.channel_layer.group_add(ALL_DISPLAYS_GROUP, self.channel_name)
        await self.accept()

        state = await self._register()
        await self.send_json({"type": "welcome", **state})
        logger.info("Display %s connected", self.slug)

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)
            await self.channel_layer.group_discard(ALL_DISPLAYS_GROUP, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "heartbeat":
            await self._touch()
            await self.send_json({"type": "heartbeat.ack"})

    async def display_message(self, event):
        """Relay a bus message down to the browser."""
        await self.send_json(event["payload"])

    # ── db ─────────────────────────────────────────────────────────────────────
    @database_sync_to_async
    def _register(self) -> dict:
        from nora_home.displays.models import Display

        display, created = Display.objects.get_or_create(
            slug=self.slug,
            defaults={"name": self.slug.title(),
                      "kind": (Display.Kind.WALL
                               if self.slug == settings.NORA_HOME_MAIN_DISPLAY_SLUG
                               else Display.Kind.AMBIENT)},
        )
        if created:
            logger.info("Registered new display %s", self.slug)
        display.touch()
        return {
            "slug": display.slug,
            "panel": display.current_panel,
            "rotation": display.rotation_enabled and not display.is_pinned,
            "rotation_seconds": display.rotation_seconds,
            "night_mode": display.in_night_mode(),
        }

    @database_sync_to_async
    def _touch(self):
        from django.utils import timezone

        from nora_home.displays.models import Display

        Display.objects.filter(slug=self.slug).update(last_seen_at=timezone.now())


class KioskConsumer(AsyncJsonWebsocketConsumer):
    """The sending end: the small touchscreen that drives the big one."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.username = user.get_username()
        await self.channel_layer.group_add(group_for(settings.NORA_HOME_KIOSK_DISPLAY_SLUG),
                                           self.channel_name)
        await self.accept()
        await self.send_json({"type": "welcome",
                              "controls": settings.NORA_HOME_MAIN_DISPLAY_SLUG})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(
            group_for(settings.NORA_HOME_KIOSK_DISPLAY_SLUG), self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        if action not in KIOSK_ACTIONS:
            logger.warning("Kiosk sent unknown action %r", action)
            await self.send_json({"type": "error", "message": f"unknown action {action}"})
            return

        target = content.get("display") or settings.NORA_HOME_MAIN_DISPLAY_SLUG
        payload = {"type": action, **{k: v for k, v in content.items()
                                      if k not in {"action", "display"}}}

        if action in {"show", "pin"}:
            await self._persist_show(target, content)

        await self.channel_layer.group_send(
            group_for(target), {"type": "display.message", "payload": payload})
        await self.send_json({"type": "ack", "action": action, "display": target})

    async def display_message(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def _persist_show(self, target: str, content: dict):
        from nora_home.displays.bus import show_panel

        show_panel(target, str(content.get("panel", ""))[:120],
                   pin_seconds=int(content.get("pin_seconds", 0) or 0),
                   issued_by=self.username)
