"""
Sound — the one channel that cannot deliver anything itself.

Every other channel in this package posts, DMs, or writes a row from inside
the container. This one can't: the speakers are physically wired to the Pi's
HDMI output, on the host, and Django runs in Docker with no path to it — the
same boundary the wall power schedule crosses
(`nora_home.core.management.commands.wall_power_state`), solved the same way.

**`send()` does not play a sound. It writes the resolved audio to a
host-visible cache and stops.** A small host-side script, on a systemd timer,
is what actually calls `aplay` — see `docker/entrypoint.sh` §"slack" for the
sibling pattern (a container that only decides) and
`scripts/lib/provision-pi.sh` for the timer itself.

**What "resolved" means is entirely `nora_home.todo.alarms`'s decision** — this
channel only knows a task id and hands it straight to `resolve_alarm()`. Not
`alarm_kind`/`alarm_ref` themselves, and not the audio bytes: `context` is a
`JSONField`, so anything here has to survive a database round trip, and raw
audio does not. Resolving fresh, on delivery, is also simply correct — the
task's alarm could have changed between the reminder firing and this channel
running.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from django.conf import settings

from nora_home.notifications.channels import BaseChannel, ChannelError

logger = logging.getLogger(__name__)

# Nothing physically playing this house's one set of speakers needs to look
# further back than this — old files are debris from a run the host script
# never got to (a crash, a reboot mid-cycle), not a queue to work through.
STALE_AFTER_SECONDS = 3600

# Not `mimetypes.guess_extension()` — checked rather than assumed, and it
# returns None for "audio/wav" on stock Python (only the legacy
# "audio/x-wav" maps to .wav in the stdlib's table), so every chime this
# channel ever wrote landed as a silently wrong "N.bin" until this was
# caught running the real pipeline end to end on the house. The two content
# types nora_home.todo.alarms actually produces are worth naming exactly
# rather than trusting a guesser tuned for arbitrary uploads.
EXTENSIONS = {
    "audio/wav": ".wav",
    "audio/mpeg": ".mp3",
}


class SoundChannel(BaseChannel):
    name = "sound"

    def is_configured(self) -> bool:
        # Always "configured": writing to the cache directory needs nothing
        # from the environment. Whether anything is physically connected to
        # play it back is the host script's problem, not this channel's.
        return True

    def send(self, notification, delivery) -> dict:
        context = notification.context or {}
        audio = self._resolve(context)
        if audio is None:
            raise ChannelError(
                "This notification carries neither an alarm_task_id nor "
                "speech_text, so there is nothing to play.")

        data, content_type = audio
        extension = EXTENSIONS.get(content_type, ".bin")
        cache_dir = Path(settings.NORA_HOME_ALARM_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)
        _prune_stale(cache_dir)

        filename = f"{delivery.pk}{extension}"
        (cache_dir / filename).write_bytes(data)

        return {"target": "wall-speakers", "ref": filename}

    def _resolve(self, context: dict) -> tuple[bytes, str] | None:
        """The audio this notification is asking for, from whichever of the two
        sources it names — or `None` if it names neither.

        **Two sources, both references rather than bytes**, for the reason in
        this module's docstring: `context` is a JSONField.

        * `alarm_task_id` — Todo's own alarms. The task's `alarm_kind` decides
          what it resolves to, and it is re-resolved here rather than at queue
          time because the task's alarm could have changed in between.
        * `speech_text` — anything in the house calling
          `nora_home.notifications.speech.speak()`. Synthesised here, in the
          worker, for the same reason: this is where the vendor call belongs,
          off whatever request or sweep asked for it.
        """
        task_id = context.get("alarm_task_id")
        if task_id:
            from nora_home.todo.alarms import resolve_alarm
            from nora_home.todo.models import Task

            task = Task.objects.filter(pk=task_id).first()
            audio = resolve_alarm(task) if task else None
            if audio is None:
                raise ChannelError(
                    f"No alarm audio could be resolved for task {task_id}.")
            return audio

        text = (context.get("speech_text") or "").strip()
        if text:
            from nora_home.notifications.tts import TTSError, get_provider

            try:
                return get_provider().synthesize(text)
            except TTSError as exc:
                # A ChannelError, not a silent pass: unlike a Todo alarm — which
                # degrades to "this task has no alarm" — somebody explicitly
                # asked the house to say this, so the failure is worth a failed
                # Delivery row and a line on the House log.
                raise ChannelError(f"Could not synthesise speech: {exc}") from exc

        return None


def _prune_stale(cache_dir: Path) -> None:
    cutoff = time.time() - STALE_AFTER_SECONDS
    for entry in cache_dir.iterdir():
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            # Another process (the host script) may be mid-read of this exact
            # file; losing a prune this cycle is nothing, raising here would
            # take the whole alarm down over housekeeping.
            logger.debug("Could not prune stale alarm file %s", entry, exc_info=True)
