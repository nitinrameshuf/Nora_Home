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
# payload unparsed — see KioskConsumer.receive_json).
#
# This list is deliberately only what wall-live.js actually implements. It used
# to also carry show/pin/unpin/next/previous/brightness/sleep/wake, all of which
# belonged to the pre-rendered ambient wall that the iframe wall replaced — the
# server happily relayed them and the wall silently ignored every one, so a
# kiosk button wired to any of them looked functional and did nothing.
#
# Story 51 adds two, and they are different shapes: `scroll` is relayed to the
# screen like the others (wall-live.js grew a handler for it in the same
# commit, which is what the rule above demands), while `zoom` is handled
# server-side — it writes a house setting and turns into a `refresh`, so the
# wall needs no handler for it at all.
KIOSK_ACTIONS = {"navigate", "refresh", "say", "scroll", "zoom", "volume"}

# The subset that is *not* relayed verbatim, and so is exempt from the
# "wall-live.js must implement it" rule the test enforces.
SERVER_SIDE_ACTIONS = {"zoom", "volume"}


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
        # Just the identity. This used to also send panel/rotation/night_mode,
        # which wall-live.js has never read — the iframe wall shows whatever
        # page it was sent to, and screen power is host-side.
        return {"slug": display.slug}

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
        await self._register()
        await self.send_json({"type": "welcome",
                              "controls": settings.NORA_HOME_MAIN_DISPLAY_SLUG})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(
            group_for(settings.NORA_HOME_KIOSK_DISPLAY_SLUG), self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "heartbeat":
            await self._touch()
            await self.send_json({"type": "heartbeat.ack"})
            return

        action = content.get("action")
        if action not in KIOSK_ACTIONS:
            logger.warning("Kiosk sent unknown action %r", action)
            await self.send_json({"type": "error", "message": f"unknown action {action}"})
            return

        target = content.get("display") or settings.NORA_HOME_MAIN_DISPLAY_SLUG

        # Most actions are relayed straight through to the screen. `zoom` is
        # not: it changes a stored house setting, and the screen only needs to
        # be told to reload afterwards, so it is handled here and turns into a
        # refresh (Story 51).
        if action == "zoom":
            zoom = await self._apply_zoom(target, content.get("delta"))
            await self.channel_layer.group_send(
                group_for(target), {"type": "display.message",
                                    "payload": {"type": "refresh"}})
            await self.send_json({"type": "ack", "action": action,
                                  "display": target, "zoom": zoom})
            return

        # Volume is a house-wide setting, not a property of one screen, so it
        # is applied here and the screens are told nothing at all — the next
        # sound the house makes is simply quieter (there is no mixer on the
        # host to call; see nora_home/notifications/volume.py).
        if action == "volume":
            level = await self._apply_volume(content.get("delta"))
            await self.send_json({"type": "ack", "action": action,
                                  "display": target, "volume": level})
            return

        payload = {"type": action, **{k: v for k, v in content.items()
                                      if k not in {"action", "display"}}}

        await self.channel_layer.group_send(
            group_for(target), {"type": "display.message", "payload": payload})
        await self.send_json({"type": "ack", "action": action, "display": target})

    @database_sync_to_async
    def _apply_volume(self, delta):
        """Nudge the house's alarm volume and persist it. Returns what stuck."""
        from nora_home.notifications import volume as volume_settings

        try:
            step = float(delta)
        except (TypeError, ValueError):
            step = 0.0
        return volume_settings.save(volume_settings.stored() + step)

    @database_sync_to_async
    def _apply_zoom(self, target, delta):
        """Nudge one screen's zoom and persist it. Returns what was stored.

        Clamping lives in nora_home.ui.zoom (0.8–2.0 on the wall, 0.8–1.2 on
        the kiosk — its layout viewport drops under the 860px breakpoint
        before then), so the panel cannot drive a screen to a size that
        breaks it however many times someone presses the key.
        """
        from nora_home.ui import zoom as zoom_settings

        surface = "kiosk" if target == settings.NORA_HOME_KIOSK_DISPLAY_SLUG else "wall"
        try:
            step = float(delta)
        except (TypeError, ValueError):
            step = 0.0

        current = dict(zoom_settings.stored())
        current[surface] = zoom_settings.clamp(surface, current.get(surface, 1.0) + step)
        return zoom_settings.save(current)[surface]

    async def display_message(self, event):
        await self.send_json(event["payload"])

    # ── db ─────────────────────────────────────────────────────────────────────
    # The kiosk is a Display row too (kind=KIOSK) — without these, nothing ever
    # marks it online: it only sends commands, never listens on the wall's group,
    # so it never went through DisplayConsumer at all.
    @database_sync_to_async
    def _register(self):
        from nora_home.displays.models import Display

        slug = settings.NORA_HOME_KIOSK_DISPLAY_SLUG
        display, created = Display.objects.get_or_create(
            slug=slug, defaults={"name": slug.title(), "kind": Display.Kind.KIOSK})
        if created:
            logger.info("Registered new display %s", slug)
        display.touch()

    @database_sync_to_async
    def _touch(self):
        from django.utils import timezone

        from nora_home.displays.models import Display

        Display.objects.filter(slug=settings.NORA_HOME_KIOSK_DISPLAY_SLUG).update(
            last_seen_at=timezone.now())
