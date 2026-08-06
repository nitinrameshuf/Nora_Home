"""
Turning a Task's `alarm_kind` / `alarm_ref` into actual playable audio
(docs/Main_App/subsystems/todo.md, "Alarms").

**The whole point of this module is that nothing downstream cares which kind
it was.** `resolve_alarm()` always returns the same shape — bytes and a content
type — or `None`. `nora_home.notifications.channels.sound.SoundChannel` writes
whatever comes back to the host-visible cache; it never branches on
`alarm_kind` itself, and neither does the host script.

Three kinds, three sources of bytes:

* **chime** — a file shipped in the image (`static/nora_home/audio/`), read
  from disk. `alarm_ref` picks which one; anything else falls back to the
  default rather than 404ing a task someone is relying on to make a sound.
* **file** — `alarm_ref` is an object-storage key, fetched via
  `nora_home.datastores.objects.get_bytes()`. Missing or unreachable storage
  degrades to `None`, not an exception — a broken upload must not silence a
  house-wide alarm timer.
* **speech** — `alarm_ref` is the text itself, synthesised through
  `nora_home.notifications.tts`. With no provider configured (the shipped
  state — see that module) this always degrades to `None` today; the call
  site treats that exactly like "nothing to play".
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings

from nora_home.todo.models import AlarmKind

logger = logging.getLogger(__name__)

# Bundled sounds a task can choose by name via alarm_ref. Keys are what a
# person picks from in the form; "default" is what an empty or unrecognised
# alarm_ref falls back to.
CHIMES = {
    "default": "chime.wav",
}

_AUDIO_DIR = Path(settings.BASE_DIR) / "static" / "nora_home" / "audio"

# A person can type anything into a speech alarm; a TTS provider and the
# eventual host playback both need a sane upper bound. Long enough for a real
# reminder, short enough that a pasted paragraph doesn't hold the house's one
# alarm slot hostage.
MAX_SPEECH_CHARS = 500


def resolve_alarm(task) -> tuple[bytes, str] | None:
    """`(audio_bytes, content_type)` for this task's configured alarm, or
    `None` if it has none, or the one it has could not be produced.

    Deliberately returns `None` rather than raising for every degraded case —
    a task with a broken alarm should behave like a task with no alarm, per
    CLAUDE.md's "failures degrade, never cascade." The reminder itself, and
    every other channel it goes out on, must not be affected by this.
    """
    if not task.alarm_kind:
        return None

    try:
        if task.alarm_kind == AlarmKind.CHIME:
            return _chime(task.alarm_ref)
        if task.alarm_kind == AlarmKind.FILE:
            return _file(task.alarm_ref)
        if task.alarm_kind == AlarmKind.SPEECH:
            return _speech(task.alarm_ref)
    except Exception:
        logger.exception("Could not resolve the %s alarm for task %s",
                         task.alarm_kind, task.pk)
        return None

    logger.warning("Task %s has an unrecognised alarm_kind %r", task.pk, task.alarm_kind)
    return None


def _chime(alarm_ref: str) -> tuple[bytes, str] | None:
    filename = CHIMES.get(alarm_ref) or CHIMES["default"]
    path = _AUDIO_DIR / filename
    if not path.is_file():
        logger.error("Bundled chime %s is missing from the image", path)
        return None
    return path.read_bytes(), "audio/wav"


def _file(alarm_ref: str) -> tuple[bytes, str] | None:
    if not alarm_ref:
        return None

    from nora_home.datastores.objects import StorageUnavailable, get_bytes

    try:
        return get_bytes(alarm_ref), "audio/mpeg"
    except (StorageUnavailable, OSError, FileNotFoundError) as exc:
        logger.warning("Could not fetch alarm file %r: %s", alarm_ref, exc)
        return None


def is_quiet_now() -> bool:
    """§"Alarms": "Sound follows the house-wide `notifications.quiet_hours`
    setting, always." Deliberately not `HouseMember.in_quiet_hours()` — that is
    one person's preference, and sound comes out of the 24" for whoever is in
    the room, so it is never an individual's call to make."""
    from django.utils import timezone

    from nora_home.core.settings_store import get_setting

    window = get_setting("notifications.quiet_hours", default={"start": 22, "end": 7})
    start, end = int(window.get("start", 22)), int(window.get("end", 7))
    hour = timezone.localtime().hour
    # Same shape as wall_power_state's own window check: a normal range when
    # start <= end, and one that wraps past midnight (22:00-07:00, the
    # default) otherwise.
    return start <= hour < end if start <= end else start <= hour or hour < end


def queue_alarm(task, instance) -> bool:
    """Resolve and queue this occasion's sound, once. Returns whether it was
    actually queued — `False` covers "no alarm configured", "quiet hours", and
    "already queued for this instance" alike, since callers only need to know
    whether a sound is now pending, not why one isn't.
    """
    if not task.alarm_kind or is_quiet_now():
        return False

    from nora_home.notifications.api import notify_house

    result = notify_house(
        title=f"Alarm: {task.title}", app_slug="todo",
        url=f"/todo/t/{task.uuid}/", channels=["sound"], sync=True,
        dedupe_key=f"alarm:{instance.uuid}", dedupe_minutes=60 * 24 * 30,
        alarm_task_id=task.pk,
    )
    return result is not None


def queue_missed_alarms_summary(tasks: list) -> None:
    """§10.4: "collapse the rest into a single 'you missed 8 reminders'
    message." Text, not sound — the house's one alarm slot for this sweep
    already went to the most recent occasion (`_queue_alarms` in reminders.py),
    and playing a second, third and fourth sound moments apart is the exact
    burst this rule exists to prevent."""
    from nora_home.notifications.api import notify_house

    titles = ", ".join(task.title for task in tasks[:5])
    if len(tasks) > 5:
        titles += f", and {len(tasks) - 5} more"

    notify_house(
        title=f"You missed {len(tasks)} alarm{'s' if len(tasks) != 1 else ''}",
        body=titles, app_slug="todo", severity="nudge",
        channels=["inapp", "slack"],
        dedupe_key=f"alarm-backlog:{':'.join(str(t.pk) for t in tasks[:20])}",
    )


def _speech(alarm_ref: str) -> tuple[bytes, str] | None:
    if not alarm_ref:
        return None

    from nora_home.notifications.tts import TTSError, get_provider

    text = alarm_ref[:MAX_SPEECH_CHARS]
    try:
        return get_provider().synthesize(text)
    except TTSError as exc:
        logger.info("Speech alarm not played (%s): %s", exc, text[:80])
        return None
