"""
The house's voice — one call, from anywhere.

    from nora_home.notifications.speech import speak

    speak("The bins go out tonight.")

That is the whole published surface. Todo's speech alarms use it, and so should
anything else that ever wants the house to say something out loud: a doorbell
announcement, a morning briefing, the robot relaying a message.

## Why this exists rather than every app calling `tts.get_provider()`

Three things have to happen between "some text" and "a noise in the kitchen",
and none of them belong in a house app:

1. **Synthesis** — vendor-specific, and already behind `tts.TTSProvider`.
2. **Quiet hours** — house-wide, never per-member, because sound comes out of
   the 24" for whoever is in the room (`todo.alarms.is_quiet_now()`).
3. **Delivery** — the audio has to reach the *host*, not the container. Only
   `SoundChannel` knows about the bind-mounted cache the host's `aplay` watches.

An app that reached for the provider directly would get step 1 and silently skip
2 and 3: it would produce correct audio, inside a container, at 3am, that nobody
would ever hear. This function is the difference between synthesising speech and
the house actually speaking.

## What it does not do

**No queueing, no mixing, no interrupting.** The house has one pair of speakers
and `SoundChannel` writes one file at a time; two `speak()` calls a second apart
are two sounds a second apart. Todo already solves the burst problem at its own
level (§10.4 — the backlog collapses into one summary rather than eight alarms),
and that is the right layer for it: only the caller knows whether its eight
things are eight separate announcements or one.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# The same ceiling `todo.alarms` applies to a speech alarm's text, for the same
# reasons — a sane upper bound for the vendor, and no single announcement
# holding the house's one speaker for a paragraph.
MAX_SPEECH_CHARS = 500


def speak(text: str, *, app_slug: str = "", title: str = "",
          respect_quiet_hours: bool = True, sync: bool = False) -> bool:
    """Say something out loud in the house. Returns whether a sound was queued.

    `False` covers every reason nothing will be heard — no text, no TTS provider
    configured, quiet hours, or a vendor failure — because the caller only needs
    to know whether the house is about to speak, not which of those it was. The
    reason is logged. **This never raises**: a house app asking for a voice must
    not be able to break itself, or its caller, by asking at 3am or before
    anyone has set an API key.

    `respect_quiet_hours=False` is for the rare thing that genuinely outranks
    the window — a smoke alarm, not a reminder. Default is to respect it.
    """
    text = (text or "").strip()[:MAX_SPEECH_CHARS]
    if not text:
        return False

    from nora_home.notifications.tts import is_configured

    # Checked here rather than discovered in the worker, because this is the
    # only place that can still tell the caller. It costs nothing — no vendor
    # call, just whether a key exists.
    if not is_configured():
        logger.info("Nothing spoken (no TTS provider configured): %s", text[:80])
        return False

    if respect_quiet_hours:
        # Imported here rather than at module scope: notifications is Level 1
        # and todo is Level 2, so the base platform must not depend on the app
        # at import time — only at the moment it actually needs the answer.
        # If Todo is ever uninstalled this degrades to "not quiet", which is
        # the right default for a house that no longer has a quiet-hours
        # setting to consult.
        try:
            from nora_home.todo.alarms import is_quiet_now
        except ImportError:
            def is_quiet_now() -> bool:
                return False
        if is_quiet_now():
            logger.info("Not speaking during quiet hours: %s", text[:80])
            return False

    from nora_home.notifications.api import notify_house

    # The *text* travels in `context`, not the audio — `SoundChannel`'s own
    # docstring is explicit that context is a JSONField and raw audio does not
    # survive a database round trip. Synthesis happens on delivery, in the
    # worker, exactly as `resolve_alarm()` re-resolves a task's alarm there.
    # So the return value means "queued", the same as `todo.alarms.queue_alarm`
    # — a vendor failure after this point shows up as a failed Delivery and on
    # the House log, which is where a failure nobody was waiting on belongs.
    notification = notify_house(
        title=title or _shorten(text),
        app_slug=app_slug or "core",
        channels=["sound"],
        sync=sync,
        # Deliberately no dedupe_key. Todo's alarms set one per instance
        # because an occasion must not be announced twice; a bare speak() call
        # is a deliberate act by whoever made it, and silently swallowing the
        # second of two identical announcements would be surprising.
        speech_text=text,
    )
    return notification is not None


def _shorten(text: str, limit: int = 60) -> str:
    """A notification title from the spoken text. The words are the point, so
    the inbox row should show them rather than a generic "Nora Home said
    something" — truncated, because a title is a line, not a paragraph."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
