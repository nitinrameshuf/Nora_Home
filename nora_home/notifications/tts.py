"""
Text-to-speech — the seam, not the vendor (docs/Main_App/subsystems/todo.md
§Alarms: "Build to the seam and stop — a provider-agnostic interface with one
implementation stubbed; the provider is chosen later.")

`TTSProvider.synthesize()` is the whole contract: text in, audio bytes out, in
a format `nora_home.todo.alarms` can hand straight to `SoundChannel` without
knowing which vendor produced it. `UnconfiguredTTS` is the one implementation
this story ships — it raises rather than fakes a voice, which is what lets
`resolve_alarm()` degrade a speech alarm to silence (or, better, notify the
owner their alarm needs a provider) instead of the whole reminder pipeline
failing because nobody picked a vendor yet.

Wiring in a real provider later means one new class here and a setting to
choose it — nothing at any call site changes.
"""

from __future__ import annotations


class TTSError(Exception):
    """Speech could not be produced. Callers treat this the way `SlackChannel`
    treats a missing token — a configuration gap, not a bug — and degrade."""


class TTSProvider:
    """Subclass this and implement `synthesize()`."""

    def synthesize(self, text: str) -> tuple[bytes, str]:
        """`(audio_bytes, content_type)` for the given text, or raise
        `TTSError`. Text is already trimmed to something sane by the caller —
        a provider should not have to guess a house's idea of "too long"."""
        raise NotImplementedError


class UnconfiguredTTS(TTSProvider):
    """The stub. No vendor is chosen yet, so this is honest about it rather
    than silently returning a chime instead of the words someone wrote."""

    def synthesize(self, text: str) -> tuple[bytes, str]:
        raise TTSError(
            "No text-to-speech provider is configured. Story 38 stops at the "
            "seam on purpose — see docs/Main_App/subsystems/todo.md, "
            "'Alarms'. A speech alarm needs a real TTSProvider wired in "
            "before it can play.")


def get_provider() -> TTSProvider:
    """The provider currently in force. One place to change when a real
    vendor is chosen, so nothing importing this module has to."""
    return UnconfiguredTTS()
