"""
Alarms — turning a Task's `alarm_kind`/`alarm_ref` into a real sound
(docs/Main_App/subsystems/todo.md, "Alarms").

Three modules, tested at the seam each one actually owns:

* `nora_home.notifications.tts` — the provider interface, and the fact its
  one shipped implementation is honest about not being a real one.
* `nora_home.todo.alarms` — resolving a task's alarm to bytes, house-wide
  quiet hours, and the backlog-collapse rule (§10.4).
* `nora_home.notifications.channels.sound` — writing the resolved bytes to
  the host-visible cache, which is the one thing this channel can actually do
  from inside a container with no path to the speakers.

Nothing here touches a real host or plays a real sound — CI has no speakers,
and the whole point of the design is that Django never assumes it does.
"""

from __future__ import annotations

from datetime import time

import pytest
from django.core.cache import cache
from django.utils import timezone

from nora_home.core.settings_store import set_setting
from nora_home.notifications.channels import ChannelError
from nora_home.notifications.channels.sound import SoundChannel
from nora_home.notifications.models import Delivery, Notification
from nora_home.notifications.tts import TTSError, UnconfiguredTTS, get_provider
from nora_home.todo import alarms
from nora_home.todo.models import AlarmKind, Priority, Reminder, Task
from nora_home.todo.reminders import send_due_reminders
from nora_home.todo.scheduling import materialize

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_settings_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def make_task(member):
    """Pins `due_time` so a task due "today" is due from midnight, not 09:00.

    `alarm_task` below sets `due_at` directly and does not need this; the other
    tests here that call `materialize()` do. See that fixture's docstring, and
    `_never_quiet` below — this file has *two* independent ways of depending on
    what time the suite runs.
    """
    def _make(**kwargs):
        kwargs.setdefault("due_time", time(0, 0))
        kwargs.setdefault("title", "Take the medicine")
        kwargs.setdefault("owner", member)
        kwargs.setdefault("priority", Priority.P2)
        return Task.objects.create(**kwargs)
    return _make


# ── the TTS seam ─────────────────────────────────────────────────────────────

def test_the_shipped_provider_is_honest_about_not_being_one():
    with pytest.raises(TTSError) as caught:
        UnconfiguredTTS().synthesize("water the plants")

    assert "No text-to-speech provider" in str(caught.value)


def test_get_provider_returns_something_usable():
    provider = get_provider()

    with pytest.raises(TTSError):
        provider.synthesize("anything")


# ── resolving a task's alarm ─────────────────────────────────────────────────

def test_a_task_with_no_alarm_resolves_to_nothing(make_task):
    task = make_task()

    assert alarms.resolve_alarm(task) is None


def test_the_bundled_chime_resolves_to_real_bytes(make_task):
    task = make_task(alarm_kind=AlarmKind.CHIME, alarm_ref="default")

    result = alarms.resolve_alarm(task)

    assert result is not None
    data, content_type = result
    assert len(data) > 0
    assert content_type == "audio/wav"


def test_an_unrecognised_chime_name_falls_back_to_default(make_task):
    """A task pointing at a chime that no longer exists must still make a
    sound — falling silent because someone renamed a bundled asset is a worse
    failure than playing the wrong chime."""
    task = make_task(alarm_kind=AlarmKind.CHIME, alarm_ref="does-not-exist")

    assert alarms.resolve_alarm(task) is not None


def test_a_speech_alarm_degrades_to_nothing_without_a_provider(make_task):
    """§"Alarms": build to the seam and stop. With UnconfiguredTTS in force,
    a speech alarm must behave like a task with no alarm at all — not raise,
    not break the reminder pipeline around it."""
    task = make_task(alarm_kind=AlarmKind.SPEECH, alarm_ref="take your medicine")

    assert alarms.resolve_alarm(task) is None


def test_a_file_alarm_with_no_reference_resolves_to_nothing(make_task):
    task = make_task(alarm_kind=AlarmKind.FILE, alarm_ref="")

    assert alarms.resolve_alarm(task) is None


def test_a_file_alarm_pointing_at_missing_storage_degrades_quietly(make_task):
    """Object storage being unreachable is exactly the kind of thing that must
    not silence a house-wide alarm timer (CLAUDE.md: "failures degrade, never
    cascade"). NORA_HOME_S3_ENABLED is off in the test settings, so this
    exercises the real degrade path, not a mock of it."""
    task = make_task(alarm_kind=AlarmKind.FILE, alarm_ref="uploads/nonexistent.mp3")

    assert alarms.resolve_alarm(task) is None


def test_an_unrecognised_alarm_kind_does_not_raise(make_task):
    task = make_task(alarm_kind=AlarmKind.CHIME, alarm_ref="default")
    Task.objects.filter(pk=task.pk).update(alarm_kind="nonsense")
    task.refresh_from_db()

    assert alarms.resolve_alarm(task) is None


# ── house-wide quiet hours ───────────────────────────────────────────────────

def test_quiet_hours_default_to_the_platform_wide_window():
    """No setting saved yet — must still behave sanely rather than crash on a
    freshly provisioned house that has never touched /admin/."""
    assert isinstance(alarms.is_quiet_now(), bool)


def test_a_normal_daytime_window_is_not_quiet():
    set_setting("notifications.quiet_hours", {"start": 9, "end": 17})
    now = timezone.localtime()

    is_quiet = alarms.is_quiet_now()
    in_window = 9 <= now.hour < 17
    assert is_quiet == in_window


def test_an_overnight_window_wraps_past_midnight():
    """22:00-07:00 (the default) can't be expressed as a plain start<=hour<end
    range — this is the same wraparound wall_power_state already has to
    handle, checked the same way rather than reinvented."""
    set_setting("notifications.quiet_hours", {"start": 22, "end": 7})
    now = timezone.localtime()

    is_quiet = alarms.is_quiet_now()
    in_window = now.hour >= 22 or now.hour < 7
    assert is_quiet == in_window


def test_quiet_hours_is_house_wide_not_per_member(make_task, member):
    """§"Alarms": "not the individual's call to make." A member's own
    quiet-hours preference must have no bearing on whether the house makes a
    sound — only the one house-wide setting does."""
    member.quiet_hours_start = 0
    member.quiet_hours_end = 0
    member.save(update_fields=["quiet_hours_start", "quiet_hours_end"])
    set_setting("notifications.quiet_hours", {"start": 0, "end": 24})

    assert alarms.is_quiet_now() is True


# ── queueing an alarm ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _never_quiet(db):
    """Take the house out of quiet hours for every test in this file.

    Sound follows the house-wide `notifications.quiet_hours` window, which
    defaults to 22:00-07:00 — so `queue_alarm()` correctly refuses to make a
    noise at midnight, and four tests here that assert an alarm *does* queue
    failed on the Pi at 00:12 for that reason. They were right about the code
    and wrong to leave the window implicit.

    start == end reads as "never quiet" in `is_quiet_now()`: the non-wrapping
    branch evaluates `0 <= hour < 0`, which no hour satisfies. The three tests
    that are genuinely *about* quiet hours set their own window and override
    this.
    """
    from nora_home.core.settings_store import set_setting

    set_setting("notifications.quiet_hours", {"start": 0, "end": 0},
                app_slug="notifications")


@pytest.fixture
def alarm_task(make_task):
    """A task whose one instance is due right now — set explicitly, not left
    to materialize()'s default-due-hour fallback. That fallback is a real
    9am-unless-configured guess, and a suite that happens to run before it
    would find nothing due (see progress.md's write-up of the same trap in
    test_todo_reminders.py). Setting due_at directly is what every other
    fixture like this one in the suite already does."""
    task = make_task(alarm_kind=AlarmKind.CHIME, alarm_ref="default",
                     due_on=timezone.localdate())
    materialize(task)
    instance = task.instances.get()
    instance.due_at = timezone.now() - timezone.timedelta(minutes=1)
    instance.save(update_fields=["due_at"])
    # materialize() only creates the Instance — a Reminder is a separate row
    # the create/edit views add via ensure_default_reminder(). Constructing
    # the task through the ORM directly, as every fixture here does, has to
    # add it explicitly too, or send_due_reminders() finds nothing to fire.
    Reminder.objects.create(task=task, offset_minutes=0)
    return task


def test_queue_alarm_creates_a_sound_delivery(alarm_task):
    instance = alarm_task.instances.get()

    queued = alarms.queue_alarm(alarm_task, instance)

    assert queued is True
    delivery = Delivery.objects.get(channel="sound")
    assert delivery.notification.context["alarm_task_id"] == alarm_task.pk


def test_queue_alarm_is_a_no_op_without_an_alarm_kind(make_task):
    task = make_task(due_on=timezone.localdate())
    materialize(task)
    instance = task.instances.get()

    assert alarms.queue_alarm(task, instance) is False
    assert not Delivery.objects.filter(channel="sound").exists()


def test_queue_alarm_is_suppressed_during_quiet_hours(alarm_task):
    set_setting("notifications.quiet_hours", {"start": 0, "end": 24})
    instance = alarm_task.instances.get()

    assert alarms.queue_alarm(alarm_task, instance) is False


def test_queue_alarm_fires_at_most_once_per_instance(alarm_task):
    """The same dedupe_key mechanism every other reminder already relies on —
    not a second, bespoke 'already alarmed' flag."""
    instance = alarm_task.instances.get()

    alarms.queue_alarm(alarm_task, instance)
    alarms.queue_alarm(alarm_task, instance)

    assert Delivery.objects.filter(channel="sound").count() == 1


def test_the_missed_alarms_summary_is_text_not_sound(make_task):
    tasks = [make_task(title=f"Task {i}") for i in range(3)]

    alarms.queue_missed_alarms_summary(tasks)

    notification = Notification.objects.get(app_slug="todo", title__startswith="You missed")
    assert "3 alarms" in notification.title
    for task in tasks:
        assert task.title in notification.body


def test_the_missed_alarms_summary_caps_the_listed_titles(make_task):
    tasks = [make_task(title=f"Task {i}") for i in range(8)]

    alarms.queue_missed_alarms_summary(tasks)

    body = Notification.objects.get(app_slug="todo").body
    assert "3 more" in body


# ── the SoundChannel ──────────────────────────────────────────────────────────

def _sound_delivery(*, task_id) -> Delivery:
    notification = Notification.objects.create(
        app_slug="todo", title="Alarm", severity="info",
        context={"alarm_task_id": task_id})
    return Delivery.objects.create(notification=notification, channel="sound")


def test_sound_channel_writes_the_resolved_audio_to_the_cache(settings, tmp_path, alarm_task):
    settings.NORA_HOME_ALARM_CACHE_DIR = tmp_path
    delivery = _sound_delivery(task_id=alarm_task.pk)

    result = SoundChannel().send(delivery.notification, delivery)

    written = tmp_path / result["ref"]
    assert written.is_file()
    assert written.read_bytes() == alarms.resolve_alarm(alarm_task)[0]
    assert result["target"] == "wall-speakers"


def test_a_wav_chime_is_written_with_a_wav_extension(settings, tmp_path, alarm_task):
    """Regression test for a real bug found running this on the house:
    mimetypes.guess_extension("audio/wav") returns None on stock Python (only
    the legacy "audio/x-wav" is in its table), so every chime silently landed
    as "<id>.bin" until this was caught. aplay likely still plays a WAV by its
    header regardless of extension, but a wrong filename is still wrong."""
    settings.NORA_HOME_ALARM_CACHE_DIR = tmp_path
    delivery = _sound_delivery(task_id=alarm_task.pk)

    result = SoundChannel().send(delivery.notification, delivery)

    assert result["ref"].endswith(".wav")


def test_sound_channel_raises_when_the_task_is_gone(settings, tmp_path):
    settings.NORA_HOME_ALARM_CACHE_DIR = tmp_path
    delivery = _sound_delivery(task_id=999999)

    with pytest.raises(ChannelError):
        SoundChannel().send(delivery.notification, delivery)


def test_sound_channel_raises_without_an_alarm_task_id(tmp_path, settings):
    settings.NORA_HOME_ALARM_CACHE_DIR = tmp_path
    notification = Notification.objects.create(app_slug="todo", title="No context",
                                                severity="info")
    delivery = Delivery.objects.create(notification=notification, channel="sound")

    with pytest.raises(ChannelError):
        SoundChannel().send(notification, delivery)


def test_sound_channel_prunes_files_older_than_an_hour(settings, tmp_path, alarm_task):
    import os
    import time

    settings.NORA_HOME_ALARM_CACHE_DIR = tmp_path
    stale = tmp_path / "old.wav"
    tmp_path.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"stale")
    old_time = time.time() - 7200
    os.utime(stale, (old_time, old_time))

    delivery = _sound_delivery(task_id=alarm_task.pk)
    SoundChannel().send(delivery.notification, delivery)

    assert not stale.exists()


def test_sound_is_always_reported_configured():
    """Unlike Slack, this channel needs no token — writing to a local
    directory needs nothing from the environment. Whether a speaker is
    physically attached is the host script's problem."""
    assert SoundChannel().is_configured() is True


# ── the end-to-end path through send_due_reminders ───────────────────────────

def test_a_due_alarm_task_gets_a_sound_delivery_through_the_real_sweep(alarm_task):
    """Through send_due_reminders() itself, not queue_alarm() directly — this
    is the path that actually runs on the house's 5-minute beat schedule."""
    send_due_reminders()

    assert Delivery.objects.filter(channel="sound",
                                   notification__context__alarm_task_id=alarm_task.pk
                                   ).exists()


def test_a_task_with_no_alarm_gets_no_sound_delivery(make_task):
    task = make_task(due_on=timezone.localdate())
    materialize(task)
    instance = task.instances.get()
    instance.due_at = timezone.now() - timezone.timedelta(minutes=1)
    instance.save(update_fields=["due_at"])
    Reminder.objects.create(task=task, offset_minutes=0)

    result = send_due_reminders()

    assert result["sent"] == 1  # the reminder itself still fires normally
    assert not Delivery.objects.filter(channel="sound").exists()


def test_only_the_most_recent_of_several_due_alarms_plays(member):
    """§10.4: several alarms landing in the same sweep — the Pi having been
    off, say — must not become several sounds back to back."""
    earlier = Task.objects.create(title="Earlier", owner=member, priority=Priority.P2,
                                  alarm_kind=AlarmKind.CHIME, alarm_ref="default",
                                  due_on=timezone.localdate())
    later = Task.objects.create(title="Later", owner=member, priority=Priority.P2,
                                alarm_kind=AlarmKind.CHIME, alarm_ref="default",
                                due_on=timezone.localdate())
    materialize(earlier)
    materialize(later)
    # due_at set explicitly and in the past for both, same reason as the
    # alarm_task fixture — materialize()'s default-hour fallback depends on
    # the wall clock the suite happens to run at. earlier/later also need a
    # real, unambiguous ordering between them.
    from datetime import timedelta
    now = timezone.now()
    earlier_instance = earlier.instances.get()
    earlier_instance.due_at = now - timedelta(minutes=5)
    earlier_instance.save(update_fields=["due_at"])
    later_instance = later.instances.get()
    later_instance.due_at = now - timedelta(minutes=1)
    later_instance.save(update_fields=["due_at"])
    Reminder.objects.create(task=earlier, offset_minutes=0)
    Reminder.objects.create(task=later, offset_minutes=0)

    send_due_reminders()

    sound_deliveries = Delivery.objects.filter(channel="sound")
    assert sound_deliveries.count() == 1
    assert sound_deliveries.first().notification.context["alarm_task_id"] == later.pk
    # The one that lost its sound slot is not simply dropped — it becomes the
    # text summary, per §10.4.
    summary = Notification.objects.get(title__startswith="You missed")
    assert earlier.title in summary.body


def test_a_single_due_alarm_needs_no_summary(alarm_task):
    send_due_reminders()

    assert not Notification.objects.filter(title__startswith="You missed").exists()


def test_reminders_still_go_out_alongside_a_queued_alarm(alarm_task, member):
    """Sound is additive, not a replacement for the reminder itself — the
    person still gets a normal notification on their usual channels."""
    send_due_reminders()

    assert Notification.objects.filter(recipient=member,
                                       title=f"Due: {alarm_task.title}").exists()
