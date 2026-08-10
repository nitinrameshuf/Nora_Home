"""
The house's voice — `nora_home.notifications.tts` and `.speech`.

Two things are worth testing here and neither is "does Groq work". The vendor
call is mocked throughout: hitting a paid API from a suite that has to run
offline, on every laptop, in seconds, would trade every property this suite has
for a fact one manual run establishes better.

What is tested is **everything around** the vendor: that a missing key degrades
instead of raising, that quiet hours are respected, that the text — never the
audio — is what travels through the notification, and that a vendor failure
lands as a failed Delivery rather than taking a reminder sweep down with it.
"""

from __future__ import annotations

import sys
import types

import pytest

from nora_home.notifications import speech
from nora_home.notifications.tts import (
    GroqTTS,
    TTSError,
    UnconfiguredTTS,
    get_provider,
    is_configured,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def fake_groq(monkeypatch):
    """A stand-in for the `groq` package, injected into `sys.modules`.

    `GroqTTS.synthesize()` imports it inside the method (it is an optional
    dependency), so this is enough to intercept it without the real package
    being installed at all — which is also what makes this test file safe on a
    machine that has never run `pip install groq`.
    """
    calls = []

    class _Response:
        def read(self):
            return b"RIFF....fake wav bytes"

    class _Speech:
        def create(self, **kwargs):
            calls.append(kwargs)
            return _Response()

    class _Audio:
        speech = _Speech()

    class _Client:
        def __init__(self, api_key=None):
            calls.append({"api_key": api_key})
            self.audio = _Audio()

    module = types.ModuleType("groq")
    module.Groq = _Client
    monkeypatch.setitem(sys.modules, "groq", module)
    return calls


# ── choosing a provider ──────────────────────────────────────────────────────

def test_the_house_ships_without_a_voice(settings):
    """"none" is the default so a fresh install boots and runs reminders with
    no key at all — only spoken alarms go quiet."""
    settings.NORA_HOME_TTS_PROVIDER = "none"

    assert isinstance(get_provider(), UnconfiguredTTS)
    assert is_configured() is False


def test_choosing_groq_gives_the_groq_provider(settings):
    settings.NORA_HOME_TTS_PROVIDER = "groq"
    settings.NORA_HOME_GROQ_API_KEY = "gsk_test"

    provider = get_provider()

    assert isinstance(provider, GroqTTS)
    assert is_configured() is True


def test_an_unknown_provider_name_falls_back_rather_than_raising(settings):
    """A typo in .env must not take down whatever imported this module — on the
    reminder path that is the whole sweep."""
    settings.NORA_HOME_TTS_PROVIDER = "elevenlabs-maybe"

    assert isinstance(get_provider(), UnconfiguredTTS)


def test_a_provider_that_cannot_be_built_falls_back(settings, monkeypatch):
    settings.NORA_HOME_TTS_PROVIDER = "groq"

    def explode(*args, **kwargs):
        raise RuntimeError("no")

    monkeypatch.setattr("nora_home.notifications.tts.GroqTTS.__init__", explode)

    assert isinstance(get_provider(), UnconfiguredTTS)


# ── the Groq provider itself ─────────────────────────────────────────────────

def test_groq_without_a_key_is_a_configuration_gap_not_a_crash(settings):
    settings.NORA_HOME_GROQ_API_KEY = ""

    with pytest.raises(TTSError) as caught:
        GroqTTS().synthesize("anything")

    assert "NORA_HOME_GROQ_API_KEY" in str(caught.value)


def test_groq_refuses_to_synthesise_nothing(settings):
    settings.NORA_HOME_GROQ_API_KEY = "gsk_test"

    with pytest.raises(TTSError):
        GroqTTS().synthesize("   ")


def test_groq_returns_wav_bytes_and_says_so(settings, fake_groq):
    settings.NORA_HOME_GROQ_API_KEY = "gsk_test"
    settings.NORA_HOME_TTS_VOICE = "hannah"
    settings.NORA_HOME_TTS_MODEL = "canopylabs/orpheus-v1-english"

    audio, content_type = GroqTTS().synthesize("the bins go out tonight")

    assert audio.startswith(b"RIFF")
    # WAV, not MP3, on purpose: `aplay` on the host plays it natively, so
    # nothing extra has to be installed on the Pi for this one path.
    assert content_type == "audio/wav"
    request = [c for c in fake_groq if "input" in c][0]
    assert request["voice"] == "hannah"
    assert request["response_format"] == "wav"


def test_every_vendor_failure_becomes_one_kind_of_error(settings, monkeypatch):
    """The SDK raises a family of types for auth, rate limits and timeouts, and
    all of them mean the same thing to the caller: this has no voice, carry on."""
    settings.NORA_HOME_GROQ_API_KEY = "gsk_test"

    class _Boom:
        def __init__(self, api_key=None):
            raise ValueError("rate limited")

    module = types.ModuleType("groq")
    module.Groq = _Boom
    monkeypatch.setitem(sys.modules, "groq", module)

    with pytest.raises(TTSError) as caught:
        GroqTTS().synthesize("hello")

    assert "rate limited" in str(caught.value)


# ── speak() ──────────────────────────────────────────────────────────────────

def test_speak_says_nothing_without_a_provider(settings):
    settings.NORA_HOME_TTS_PROVIDER = "none"

    assert speech.speak("the bins go out tonight") is False


def test_speak_says_nothing_when_there_is_nothing_to_say(settings):
    settings.NORA_HOME_TTS_PROVIDER = "groq"
    settings.NORA_HOME_GROQ_API_KEY = "gsk_test"

    assert speech.speak("") is False
    assert speech.speak("   ") is False


@pytest.fixture
def not_quiet():
    """Pin the house out of quiet hours for a test that expects speech to work.

    Without this, a test that calls speak() passes by day and fails by night:
    todo.alarms.is_quiet_now() reads the wall clock against the house-wide
    `notifications.quiet_hours` window (22:00-07:00 by default), so speak()
    correctly returns False after 22:00 and the assertions below read as a
    broken feature instead of a sleeping house.

    Found when the suite went red at 01:35 having been green at 20:00 the same
    evening. It is also the real reason three of these tests "only failed on
    the Pi" across two earlier sessions — that was never the container's
    environment, it was what time the suite happened to be run. A window of
    0-0 is never quiet: is_quiet_now()'s `start <= hour < end` can hold for no
    hour at all.
    """
    from nora_home.core.settings_store import set_setting

    set_setting("notifications.quiet_hours", {"start": 0, "end": 0})


def test_speak_queues_the_text_not_the_audio(settings, not_quiet):
    """`Notification.context` is a JSONField — SoundChannel's own docstring is
    explicit that raw audio cannot survive the round trip. The text goes in and
    synthesis happens on delivery, exactly as a task's alarm is re-resolved
    there."""
    from nora_home.notifications.models import Notification

    settings.NORA_HOME_TTS_PROVIDER = "groq"
    settings.NORA_HOME_GROQ_API_KEY = "gsk_test"

    assert speech.speak("the bins go out tonight", app_slug="todo") is True

    notification = Notification.objects.latest("created_at")
    assert notification.context["speech_text"] == "the bins go out tonight"
    assert "speech_audio" not in notification.context
    assert notification.app_slug == "todo"


def test_speak_respects_quiet_hours(settings):
    from nora_home.core.settings_store import set_setting

    settings.NORA_HOME_TTS_PROVIDER = "groq"
    settings.NORA_HOME_GROQ_API_KEY = "gsk_test"
    # 0-24 is quiet at every hour, so this cannot depend on when the suite runs
    # — the same trap that made the alarm tests fail at midnight.
    set_setting("notifications.quiet_hours", {"start": 0, "end": 24},
                app_slug="notifications")

    assert speech.speak("shh") is False


def test_something_urgent_can_override_quiet_hours(settings):
    from nora_home.core.settings_store import set_setting

    settings.NORA_HOME_TTS_PROVIDER = "groq"
    settings.NORA_HOME_GROQ_API_KEY = "gsk_test"
    set_setting("notifications.quiet_hours", {"start": 0, "end": 24},
                app_slug="notifications")

    assert speech.speak("the smoke alarm is going off",
                        respect_quiet_hours=False) is True


def test_a_long_announcement_is_trimmed(settings, not_quiet):
    from nora_home.notifications.models import Notification

    settings.NORA_HOME_TTS_PROVIDER = "groq"
    settings.NORA_HOME_GROQ_API_KEY = "gsk_test"

    speech.speak("word " * 500)

    spoken = Notification.objects.latest("created_at").context["speech_text"]
    assert len(spoken) <= speech.MAX_SPEECH_CHARS


def test_the_title_shows_the_words_that_were_spoken(settings, not_quiet):
    from nora_home.notifications.models import Notification

    settings.NORA_HOME_TTS_PROVIDER = "groq"
    settings.NORA_HOME_GROQ_API_KEY = "gsk_test"

    speech.speak("the bins go out tonight")

    assert "bins" in Notification.objects.latest("created_at").title


def test_a_long_title_is_shortened_not_wrapped():
    assert speech._shorten("x" * 200).endswith("…")
    assert len(speech._shorten("x" * 200)) <= 60


# ── SoundChannel's second source ─────────────────────────────────────────────

def test_the_sound_channel_synthesises_speech_text(settings, fake_groq, tmp_path):
    from nora_home.notifications.channels.sound import SoundChannel
    from nora_home.notifications.models import Delivery, Notification

    settings.NORA_HOME_TTS_PROVIDER = "groq"
    settings.NORA_HOME_GROQ_API_KEY = "gsk_test"
    settings.NORA_HOME_ALARM_CACHE_DIR = str(tmp_path)

    notification = Notification.objects.create(
        title="Bins", app_slug="core", context={"speech_text": "the bins go out"})
    delivery = Delivery.objects.create(notification=notification, channel="sound")

    result = SoundChannel().send(notification, delivery)

    assert result["ref"].endswith(".wav")
    assert (tmp_path / result["ref"]).read_bytes().startswith(b"RIFF")


def test_a_notification_naming_neither_source_is_an_error(settings, tmp_path):
    from nora_home.notifications.channels import ChannelError
    from nora_home.notifications.channels.sound import SoundChannel
    from nora_home.notifications.models import Delivery, Notification

    settings.NORA_HOME_ALARM_CACHE_DIR = str(tmp_path)
    notification = Notification.objects.create(title="Nothing", app_slug="core")
    delivery = Delivery.objects.create(notification=notification, channel="sound")

    with pytest.raises(ChannelError):
        SoundChannel().send(notification, delivery)


def test_a_vendor_failure_on_delivery_is_a_failed_delivery(settings, tmp_path, monkeypatch):
    """Unlike a Todo alarm — which degrades to "this task has no alarm" —
    somebody explicitly asked the house to say this, so it earns a failed
    Delivery row and a line on the House log rather than silence."""
    from nora_home.notifications.channels import ChannelError
    from nora_home.notifications.channels.sound import SoundChannel
    from nora_home.notifications.models import Delivery, Notification

    settings.NORA_HOME_TTS_PROVIDER = "groq"
    settings.NORA_HOME_GROQ_API_KEY = ""      # configured provider, no key
    settings.NORA_HOME_ALARM_CACHE_DIR = str(tmp_path)

    notification = Notification.objects.create(
        title="Bins", app_slug="core", context={"speech_text": "the bins go out"})
    delivery = Delivery.objects.create(notification=notification, channel="sound")

    with pytest.raises(ChannelError):
        SoundChannel().send(notification, delivery)


def test_a_task_alarm_still_takes_precedence(settings, tmp_path, member):
    """The original source has to keep working untouched — this channel served
    Todo's alarms before it ever spoke."""
    from nora_home.notifications.channels.sound import SoundChannel
    from nora_home.notifications.models import Delivery, Notification
    from nora_home.todo.models import AlarmKind, Priority, Task

    settings.NORA_HOME_ALARM_CACHE_DIR = str(tmp_path)
    task = Task.objects.create(title="Medicine", owner=member, priority=Priority.P1,
                               alarm_kind=AlarmKind.CHIME, alarm_ref="default")

    notification = Notification.objects.create(
        title="Alarm", app_slug="todo", context={"alarm_task_id": task.pk})
    delivery = Delivery.objects.create(notification=notification, channel="sound")

    result = SoundChannel().send(notification, delivery)

    assert result["ref"].endswith(".wav")


# ── the suite must not reach the internet ────────────────────────────────────

def test_the_test_settings_have_no_real_credentials(settings):
    """`env()` reads the real environment and Compose passes every `.env` value
    into the container, so on the Pi `./nora test` inherits the house's live
    keys unless the test settings force them off.

    This is not hypothetical: wiring Groq in (2026-08-07) made the suite pick up
    the running house's provider and **make a real, billable API call inside a
    unit test**. It surfaced only because two tests asserting the degraded path
    started failing with genuine WAV bytes — had they been written any looser it
    would have been silent, and the suite would have been quietly spending money
    and requiring network on every run.
    """
    from django.conf import settings as django_settings

    assert django_settings.NORA_HOME_TTS_PROVIDER == "none"
    assert django_settings.NORA_HOME_GROQ_API_KEY == ""
    assert django_settings.ANTHROPIC_API_KEY == ""
    assert django_settings.NORA_HOME_AI_ENABLED is False


# ── alarm volume (Story 51) ──────────────────────────────────────────────────

def _tone(peak: int = 20000, frames: int = 400) -> bytes:
    """A tiny 16-bit mono WAV whose loudest sample is `peak`."""
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"".join(
            (peak if i % 2 else -peak).to_bytes(2, "little", signed=True)
            for i in range(frames)))
    return buf.getvalue()


def _peak(data: bytes) -> int:
    import io
    import wave

    with wave.open(io.BytesIO(data), "rb") as r:
        frames = r.readframes(r.getnframes())
    return max(abs(int.from_bytes(frames[i:i + 2], "little", signed=True))
               for i in range(0, len(frames) - 1, 2))


def test_volume_scales_the_samples_because_the_pi_has_no_mixer():
    """Story 51 planned a host mixer call. The Pi's HDMI audio devices expose
    no ALSA mixer controls at all, so the level is applied to the samples
    before the WAV is written for the host to play."""
    from nora_home.notifications import volume

    quiet = volume.apply(_tone(), "audio/wav", level=50)

    assert _peak(quiet) == pytest.approx(10000, abs=2)


def test_full_volume_returns_the_audio_untouched():
    from nora_home.notifications import volume

    original = _tone()

    assert volume.apply(original, "audio/wav", level=100) is original


def test_a_format_we_cannot_scale_is_played_rather_than_dropped():
    """A chime someone drops in as an mp3 should still play at full volume
    rather than not at all — returning unplayable bytes would be worse than
    being loud."""
    from nora_home.notifications import volume

    blob = b"not really audio"

    assert volume.apply(blob, "audio/mpeg", level=10) is blob


def test_scaling_clamps_rather_than_wrapping():
    """An overflowing sample wraps +32767 to -32768, which is not "slightly
    too loud", it is a crack."""
    from nora_home.notifications import volume

    loud = volume.apply(_tone(peak=32000), "audio/wav", level=100 * 4)

    assert _peak(loud) <= 32767


def test_a_corrupt_wav_is_played_unchanged_rather_than_raising():
    """This runs on the delivery path — a bad file must not take the whole
    notification down."""
    from nora_home.notifications import volume

    junk = b"RIFF____WAVEfmt " + b"\x00" * 40

    assert volume.apply(junk, "audio/wav", level=25) == junk


@pytest.mark.django_db
def test_the_stored_volume_is_clamped_to_a_percentage():
    from nora_home.notifications import volume

    assert volume.save(500) == 100
    assert volume.save(-20) == 0
    assert volume.save("loud") == volume.DEFAULT_VOLUME
