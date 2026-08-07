"""
Text-to-speech — the seam, and now a real provider behind it.

`TTSProvider.synthesize()` is the whole contract: text in, `(audio_bytes,
content_type)` out, in a format `nora_home.todo.alarms` can hand straight to
`SoundChannel` without knowing which vendor produced it. Story 38 shipped only
the seam and a stub that raised; the vendor was chosen later, which is exactly
what the seam was for — wiring Groq in touched no call site.

**The house speaks through `speak()` (see `speech.py`), not through this
module.** This is the vendor layer; that is the published API. Anything in the
house that wants a voice — Todo's speech alarms today, a doorbell announcement
or a morning briefing later — calls that.

## Why the provider is chosen by setting, not by import

`get_provider()` reads `NORA_HOME_TTS_PROVIDER` and falls back to
`UnconfiguredTTS` whenever the chosen one has no credentials. That fallback is
load-bearing: a house with no key still boots, still runs its reminders, and
still plays chime and file alarms — only *speech* alarms degrade to silence,
which is the same "failures degrade, never cascade" rule the rest of the
platform follows. A missing key must never be an exception on the reminder path.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class TTSError(Exception):
    """Speech could not be produced. Callers treat this the way `SlackChannel`
    treats a missing token — a configuration gap, not a bug — and degrade."""


class TTSProvider:
    """Subclass this and implement `synthesize()`."""

    #: Shown in logs and on the Settings page so a person can tell which voice
    #: the house is currently using without reading `.env`.
    name = "unconfigured"

    def synthesize(self, text: str) -> tuple[bytes, str]:
        """`(audio_bytes, content_type)` for the given text, or raise
        `TTSError`. Text is already trimmed to something sane by the caller —
        a provider should not have to guess a house's idea of "too long"."""
        raise NotImplementedError


class UnconfiguredTTS(TTSProvider):
    """The fallback. No key, or no provider chosen — honest about it rather
    than silently returning a chime instead of the words someone wrote."""

    name = "unconfigured"

    def synthesize(self, text: str) -> tuple[bytes, str]:
        raise TTSError(
            "No text-to-speech provider is configured. Set NORA_HOME_TTS_PROVIDER "
            "and the matching API key in .env — see docs/Main_App/subsystems/"
            "notifications.md, 'Speech'.")


class GroqTTS(TTSProvider):
    """Groq's hosted Orpheus. Chosen because it needs no local model, no GPU and
    no audio toolchain on the Pi — the house asks for bytes over HTTPS and gets
    a WAV back, which is the only shape `SoundChannel` and the host playback
    script already understand.

    **WAV, not MP3, deliberately.** `aplay` on the host plays WAV natively; an
    MP3 would need a decoder installed on the Pi purely so this one path could
    work, and the file lives for seconds before being played and deleted, so the
    size difference buys nothing.
    """

    name = "groq"

    def __init__(self, api_key: str = "", *, voice: str = "", model: str = ""):
        self.api_key = api_key or settings.NORA_HOME_GROQ_API_KEY
        self.voice = voice or settings.NORA_HOME_TTS_VOICE
        self.model = model or settings.NORA_HOME_TTS_MODEL

    def synthesize(self, text: str) -> tuple[bytes, str]:
        if not self.api_key:
            raise TTSError("NORA_HOME_GROQ_API_KEY is not set.")
        if not text.strip():
            raise TTSError("Nothing to say.")

        # Imported here, not at module scope: the package is an optional
        # dependency in the same sense `anthropic` is, and a house running
        # without speech must still import this module to get the stub.
        try:
            from groq import Groq
        except ImportError as exc:  # pragma: no cover — depends on the install
            raise TTSError(
                "The `groq` package is not installed; add it to requirements "
                "and rebuild.") from exc

        try:
            response = Groq(api_key=self.api_key).audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text,
                response_format="wav",
            )
            audio = response.read()
        except Exception as exc:  # noqa: BLE001 — every vendor failure is one thing here
            # Deliberately broad. The SDK raises a family of its own exception
            # types for auth, rate limits, timeouts and bad requests, and every
            # one of them means the same thing to the one caller that matters:
            # this reminder has no voice, carry on without it. Catching them
            # individually would be a list to keep in sync with an upstream
            # package for no behavioural difference.
            raise TTSError(f"Groq TTS failed: {type(exc).__name__}: {exc}") from exc

        if not audio:
            raise TTSError("Groq TTS returned no audio.")
        return audio, "audio/wav"


#: Every provider the house knows how to build, by the name used in
#: NORA_HOME_TTS_PROVIDER. One entry per vendor; adding a second is a class
#: above and a line here, and nothing at any call site changes.
PROVIDERS = {
    "groq": GroqTTS,
    "none": UnconfiguredTTS,
}


def get_provider() -> TTSProvider:
    """The provider currently in force.

    Never raises and never returns `None` — an unknown name, a missing key or a
    provider that cannot be constructed all fall back to `UnconfiguredTTS`,
    whose `synthesize()` raises `TTSError` at the point of use where every
    caller already handles it. Failing here instead would take down whatever
    imported this module, which on the reminder path is the whole sweep.
    """
    chosen = (settings.NORA_HOME_TTS_PROVIDER or "none").strip().lower()
    provider_class = PROVIDERS.get(chosen)

    if provider_class is None:
        logger.warning("Unknown NORA_HOME_TTS_PROVIDER %r; speech is off. "
                       "Known: %s", chosen, ", ".join(sorted(PROVIDERS)))
        return UnconfiguredTTS()

    try:
        return provider_class()
    except Exception:  # noqa: BLE001 — see the docstring
        logger.exception("Could not build the %r TTS provider; speech is off", chosen)
        return UnconfiguredTTS()


def is_configured() -> bool:
    """Whether the house currently has a voice.

    The same shape as `SlackChannel.is_configured()`, and used the same way: to
    tell a person on the Settings page why a speech alarm is silent, rather than
    leaving them to work it out from an empty log.
    """
    return not isinstance(get_provider(), UnconfiguredTTS)
