"""
How loud the house speaks.

Story 51 planned this as "a host mixer call, reached the same way audio already
is — the container writes, the host acts". That turned out not to be available:
the Pi's HDMI audio devices (`vc4hdmi0`/`vc4hdmi1`) expose **no ALSA mixer
controls at all** — `amixer -c 0 scontrols` returns nothing — because Pi HDMI
audio has no hardware volume. There is nothing on the host to call.

So the level is applied where the audio is already being produced: the house
scales the samples before writing the WAV that `aplay` will play. That is
strictly better than the original plan for this house — it needs no host
script, no systemd unit, no provisioning step and no root, so it cannot drift
out of sync with the Pi the way anything in provision-pi.sh can.

`audioop` would have been the obvious tool and is **gone** — removed from the
standard library in Python 3.13, and both the Pi (3.13) and this laptop (3.14)
are past that. Scaling 16-bit frames by hand is a dozen lines and has no
dependency to lose.
"""

from __future__ import annotations

import io
import logging
import wave

logger = logging.getLogger(__name__)

SETTING_KEY = "notifications.volume"
DEFAULT_VOLUME = 100
MIN_VOLUME = 0
MAX_VOLUME = 100


def clamp(value) -> int:
    try:
        return max(MIN_VOLUME, min(MAX_VOLUME, int(round(float(value)))))
    except (TypeError, ValueError):
        return DEFAULT_VOLUME


def stored() -> int:
    from nora_home.core.settings_store import get_setting

    return clamp(get_setting(SETTING_KEY, default=DEFAULT_VOLUME))


def save(value, *, actor=None) -> int:
    from nora_home.core.audit import record
    from nora_home.core.settings_store import set_setting

    level = clamp(value)
    set_setting(SETTING_KEY, level, app_slug="notifications",
                description="How loud spoken alarms and chimes play, 0-100.")
    # The new level, not just that it changed — "why did nobody hear the
    # boiler alarm" is only answerable if the log says what it was set to.
    record("notifications", "volume.changed", actor=actor,
           subject="Alarm volume", volume=level)
    return level


def apply(data: bytes, content_type: str, level: int | None = None) -> bytes:
    """Return `data` scaled to `level` percent. Never raises.

    Anything that is not 16-bit PCM WAV comes back untouched — a chime someone
    dropped in as an mp3 should still play at full volume rather than not at
    all, and silently returning unplayable bytes would be worse than being
    loud.
    """
    if content_type not in {"audio/wav", "audio/x-wav"}:
        return data

    level = stored() if level is None else clamp(level)
    if level == 100:
        return data

    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            params = source.getparams()
            frames = source.readframes(params.nframes)

        if params.sampwidth != 2:      # not 16-bit — leave it alone
            return data

        scaled = _scale_16bit(frames, level / 100.0)

        out = io.BytesIO()
        with wave.open(out, "wb") as sink:
            sink.setparams(params)
            sink.writeframes(scaled)
        return out.getvalue()
    except Exception:
        logger.exception("Could not scale audio to %s%%; playing it unchanged", level)
        return data


def _scale_16bit(frames: bytes, factor: float) -> bytes:
    """Scale signed little-endian 16-bit samples, clamping rather than wrapping.

    Clamping matters: an overflowing sample wraps from +32767 to -32768, which
    is not "slightly too loud", it is a crack. Nothing here scales *up* today
    (the ceiling is 100%), but the guard costs nothing and stops that being a
    surprise if it ever does.
    """
    out = bytearray(len(frames))
    for i in range(0, len(frames) - 1, 2):
        sample = int.from_bytes(frames[i:i + 2], "little", signed=True)
        value = int(sample * factor)
        value = max(-32768, min(32767, value))
        out[i:i + 2] = value.to_bytes(2, "little", signed=True)
    return bytes(out)
