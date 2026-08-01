"""
The home bot socket.

(The bot on screen is Nora Home's own face — not Nora the robot, which is a
separate machine with its own project. Nothing here talks to the robot.)

Every logged-in browser holds one. It carries three things:
  server → browser   things for the bot to say, react to, or badge
  browser → server   "the user did something" beats, so it can respond in kind
  both ways          a heartbeat, so an idle tab reconnects cleanly

A notification addressed to one member is filtered here rather than in the browser,
so one person's alerts never arrive in someone else's tab.
"""

from __future__ import annotations

import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from nora_home.ui.bot import BOT_GROUP

logger = logging.getLogger(__name__)

# Things a browser is allowed to tell the server about.
CLIENT_EVENTS = {"heartbeat", "interaction", "idle", "poke"}


class HomeBotConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.username = user.get_username()
        await self.channel_layer.group_add(BOT_GROUP, self.channel_name)
        await self.accept()
        await self.send_json({"type": "hello", "member": self.username})

    async def disconnect(self, code):
        if hasattr(self, "username"):
            await self.channel_layer.group_discard(BOT_GROUP, self.channel_name)

    async def receive_json(self, content, **kwargs):
        event = content.get("type")
        if event not in CLIENT_EVENTS:
            return
        if event == "heartbeat":
            await self.send_json({"type": "heartbeat.ack"})
        elif event == "poke":
            # Someone clicked Nora. She should have something to say about it.
            await self.send_json({"type": "react", "mood": "celebrate"})

    async def homebot_message(self, event):
        payload = event["payload"]

        # A notification for someone else is not this tab's business.
        recipient = payload.get("recipient")
        if payload.get("type") == "notification" and recipient not in (None,
                                                                       self.username):
            return

        await self.send_json(payload)
