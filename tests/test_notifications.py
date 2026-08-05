"""
Notifications: routing, deduplication, quiet hours, and delivery receipts.

The separation of Notification (the intent) from Delivery (one attempt on one
channel) is what makes "did anyone actually see this?" answerable, so both halves
are asserted rather than just "a notification exists".

No test here contacts Slack. The Slack channel is exercised through its
`is_configured()` gate and a fake transport; a test that needed a real token
would simply not run on the Pi, which defeats the point.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from nora_home.notifications.api import notify, notify_house
from nora_home.notifications.channels import ChannelError, get_channel
from nora_home.notifications.models import Delivery, Notification, Severity
from nora_home.notifications.tasks import MAX_ATTEMPTS, deliver_notification

pytestmark = pytest.mark.django_db


# ── the basic promise ────────────────────────────────────────────────────────

def test_notify_records_the_intent(member):
    notification = notify(member, title="Water the plants", body="Four days.",
                          app_slug="plants", severity=Severity.NUDGE)

    assert notification.recipient == member
    assert notification.app_slug == "plants"
    assert notification.is_unread is True


def test_notify_queues_at_least_one_delivery(member):
    notification = notify(member, title="x")

    assert notification.deliveries.exists()


def test_notify_house_has_no_recipient(db):
    """A null recipient is what "the whole house" means — asserting it keeps the
    bell menu's own filtering honest."""
    notification = notify_house(title="Power cut", severity=Severity.CRITICAL)

    assert notification.recipient is None


def test_notify_house_reaches_slack_the_wall_and_the_bell(db):
    notification = notify_house(title="Power cut")

    assert {d.channel for d in notification.deliveries.all()} == {
        "slack", "display", "inapp"}


def test_an_overlong_title_is_truncated(member):
    assert len(notify(member, title="x" * 400).title) == 160


def test_extra_kwargs_are_kept_as_context(member):
    notification = notify(member, title="x", occurrence="abc", level=3)

    assert notification.context == {"occurrence": "abc", "level": 3}


# ── deduplication ────────────────────────────────────────────────────────────

def test_the_same_dedupe_key_is_suppressed_within_the_window(member):
    """The escalation engine relies on this: a sweep that re-fires must not
    produce a second identical alert."""
    first = notify(member, title="Overdue", dedupe_key="esc:1:2")
    second = notify(member, title="Overdue", dedupe_key="esc:1:2")

    assert first is not None
    assert second is None
    assert Notification.objects.count() == 1


def test_dedupe_is_scoped_per_recipient(member, adult):
    """Two people can each be told about the same thing — the key alone must not
    silence the second person."""
    notify(member, title="Overdue", dedupe_key="esc:1:2")
    notify(adult, title="Overdue", dedupe_key="esc:1:2")

    assert Notification.objects.count() == 2


def test_an_expired_dedupe_window_lets_the_reminder_through(member):
    old = notify(member, title="Overdue", dedupe_key="esc:1:2")
    Notification.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(hours=3))

    assert notify(member, title="Overdue", dedupe_key="esc:1:2") is not None


def test_house_wide_alerts_are_deduplicated_too(db):
    """Found by this suite, 2026-08-04: notify_house accepted a dedupe_key and
    ignored it. Every caller that passes one is a repeating source — a threshold
    on a stuck sensor, an integration that keeps failing — so each cycle put a
    fresh banner on the wall. Personal alerts were suppressed; house-wide ones,
    the loudest surface in the building, were not."""
    first = notify_house(title="Battery low", dedupe_key="threshold:battery:alert")
    second = notify_house(title="Battery low", dedupe_key="threshold:battery:alert")

    assert first is not None
    assert second is None
    assert Notification.objects.count() == 1


def test_house_dedupe_does_not_suppress_personal_alerts(member):
    """The house and one person are different audiences; sharing a key must not
    silence the person."""
    notify_house(title="Filter overdue", dedupe_key="shared-key")

    assert notify(member, title="Filter overdue", dedupe_key="shared-key") is not None


def test_no_dedupe_key_means_never_deduplicated(member):
    notify(member, title="Same")
    notify(member, title="Same")

    assert Notification.objects.count() == 2


# ── channel routing ──────────────────────────────────────────────────────────

def test_a_members_preferred_channels_are_honoured(make_member):
    person = make_member(preferred_channels=["console"])

    notification = notify(person, title="x")

    assert [d.channel for d in notification.deliveries.all()] == ["console"]


def test_an_unknown_preferred_channel_is_dropped(make_member):
    """Someone editing preferences in the admin should not be able to route their
    own alerts into a channel that does not exist."""
    person = make_member(preferred_channels=["carrier_pigeon", "console"])

    notification = notify(person, title="x")

    assert [d.channel for d in notification.deliveries.all()] == ["console"]


def test_an_explicit_channel_override_wins(member):
    notification = notify(member, title="x", channels=["console"])

    assert [d.channel for d in notification.deliveries.all()] == ["console"]


def test_disabling_notifications_still_records_them_in_app(make_member):
    """"Off" means stop pushing, not stop recording — otherwise turning
    notifications off quietly loses history."""
    person = make_member(notifications_enabled=False,
                         preferred_channels=["slack", "console"])

    notification = notify(person, title="x")

    assert [d.channel for d in notification.deliveries.all()] == ["inapp"]


def test_everyone_always_gets_at_least_one_channel(make_member):
    person = make_member(preferred_channels=["carrier_pigeon"])

    notification = notify(person, title="x")

    assert notification.deliveries.exists(), "notification was routed nowhere"


# ── quiet hours ──────────────────────────────────────────────────────────────

def _at_hour(monkeypatch, hour):
    """Pin the wall clock so quiet-hours routing is deterministic."""
    import nora_home.accounts.models as accounts

    real = accounts.HouseMember.in_quiet_hours

    def fake(self, when=None):
        return real(self, when or datetime(2026, 8, 3, hour, 30))

    monkeypatch.setattr(accounts.HouseMember, "in_quiet_hours", fake)


def test_quiet_hours_drop_push_channels(make_member, monkeypatch):
    person = make_member(preferred_channels=["slack", "inapp"],
                         quiet_hours_start=22, quiet_hours_end=7)
    _at_hour(monkeypatch, 2)

    notification = notify(person, title="Vitamins", severity=Severity.NUDGE)

    assert [d.channel for d in notification.deliveries.all()] == ["inapp"]


@pytest.mark.parametrize("severity", [Severity.ALERT, Severity.CRITICAL])
def test_urgent_alerts_ignore_quiet_hours(make_member, monkeypatch, severity):
    """A smoke alarm at 3am has to get through. This is the whole reason
    QUIET_HOURS_OVERRIDE exists."""
    person = make_member(preferred_channels=["slack", "inapp"],
                         quiet_hours_start=22, quiet_hours_end=7)
    _at_hour(monkeypatch, 2)

    notification = notify(person, title="Smoke alarm", severity=severity)

    assert "slack" in [d.channel for d in notification.deliveries.all()]


def test_outside_quiet_hours_push_channels_are_kept(make_member, monkeypatch):
    person = make_member(preferred_channels=["slack", "inapp"],
                         quiet_hours_start=22, quiet_hours_end=7)
    _at_hour(monkeypatch, 12)

    notification = notify(person, title="x", severity=Severity.NUDGE)

    assert "slack" in [d.channel for d in notification.deliveries.all()]


# ── delivery ─────────────────────────────────────────────────────────────────

def test_delivery_marks_sent_and_stamps_the_time(member):
    notification = notify(member, title="x", channels=["console"], sync=True)

    delivery = notification.deliveries.get()
    assert delivery.status == Delivery.Status.SENT
    assert delivery.sent_at is not None
    assert delivery.attempts == 1


def test_an_unconfigured_channel_is_skipped_not_retried_forever(member, settings):
    """No Slack token on this Pi yet. That should read as 'skipped', so nobody
    goes looking for a delivery bug that is really a missing credential."""
    settings.NORA_HOME_SLACK_BOT_TOKEN = ""
    settings.NORA_HOME_SLACK_WEBHOOK_URL = ""

    notification = notify(member, title="x", channels=["slack"], sync=True)

    delivery = notification.deliveries.get()
    assert delivery.status == Delivery.Status.SKIPPED
    assert "not configured" in delivery.error


def test_an_unregistered_channel_is_skipped_with_a_reason(member):
    notification = Notification.objects.create(title="x", recipient=member,
                                               app_slug="core")
    Delivery.objects.create(notification=notification, channel="telegram")

    deliver_notification(notification.pk)

    delivery = notification.deliveries.get()
    assert delivery.status == Delivery.Status.SKIPPED
    assert "not registered" in delivery.error


def test_a_failing_channel_stays_pending_for_another_attempt(member, monkeypatch):
    import nora_home.notifications.channels.console as console

    def fail(self, notification, delivery):
        raise ChannelError("service unavailable")

    monkeypatch.setattr(console.ConsoleChannel, "send", fail)
    notification = notify(member, title="x", channels=["console"], sync=True)

    delivery = notification.deliveries.get()
    assert delivery.status == Delivery.Status.PENDING
    assert delivery.attempts == 1
    assert "service unavailable" in delivery.error


def test_a_channel_that_keeps_failing_is_eventually_given_up_on(member, monkeypatch):
    """Otherwise a dead Slack would have the worker retrying one message for the
    rest of the house's life."""
    import nora_home.notifications.channels.console as console

    def fail(self, notification, delivery):
        raise ChannelError("still down")

    monkeypatch.setattr(console.ConsoleChannel, "send", fail)
    notification = notify(member, title="x", channels=["console"], sync=True)

    for _ in range(MAX_ATTEMPTS):
        deliver_notification(notification.pk)

    delivery = notification.deliveries.get()
    assert delivery.status == Delivery.Status.FAILED


def test_delivering_a_vanished_notification_is_harmless():
    assert deliver_notification(999999) == {"delivered": 0}


def test_delivery_does_not_re_send_already_sent_channels(member):
    notification = notify(member, title="x", channels=["console"], sync=True)

    deliver_notification(notification.pk)

    assert notification.deliveries.get().attempts == 1


# ── the channels themselves ──────────────────────────────────────────────────

def test_get_channel_returns_none_for_an_unknown_name():
    assert get_channel("carrier_pigeon") is None


@pytest.mark.parametrize("name", ["slack", "inapp", "display", "console"])
def test_every_configured_channel_loads(name):
    """A typo'd dotted path in settings would otherwise only surface as a
    skipped delivery at 3am."""
    assert get_channel(name) is not None


def test_the_display_channel_puts_a_banner_on_the_wall(member, settings):
    """The wall must receive `banner` specifically: it is the one message type
    wall-live.js implements for alerts. This pairing has silently broken once
    already — the channel sent, the browser had no handler, and the alert
    vanished with every layer reporting success."""
    sent = []
    import nora_home.notifications.channels.display as display_channel

    monkey = display_channel.send_to_display
    display_channel.send_to_display = lambda slug, payload: sent.append((slug, payload))
    try:
        notify(member, title="Smoke alarm", channels=["display"], sync=True)
    finally:
        display_channel.send_to_display = monkey

    assert sent, "nothing was pushed to the wall"
    slug, payload = sent[0]
    assert slug == settings.NORA_HOME_MAIN_DISPLAY_SLUG
    assert payload["type"] == "banner"
    assert payload["title"] == "Smoke alarm"


def test_slack_reports_itself_unconfigured_without_credentials(settings):
    settings.NORA_HOME_SLACK_BOT_TOKEN = ""
    settings.NORA_HOME_SLACK_WEBHOOK_URL = ""

    assert get_channel("slack").is_configured() is False


def test_slack_reports_itself_configured_with_a_webhook(settings):
    settings.NORA_HOME_SLACK_BOT_TOKEN = ""
    settings.NORA_HOME_SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/x"

    assert get_channel("slack").is_configured() is True


# ── Slack failures should say what to do ─────────────────────────────────────

def _slack_error(code):
    """Drive the real channel against a fake Slack response."""
    import nora_home.notifications.channels.slack as slack_channel

    class FakeResponse:
        content = b"{}"

        @staticmethod
        def json():
            return {"ok": False, "error": code}

    return slack_channel, FakeResponse


@pytest.mark.parametrize("code,expected_hint", [
    ("channel_not_found", "/invite"),
    ("not_in_channel", "/invite"),
    ("missing_scope", "im:write"),
    ("invalid_auth", "xoxb-"),
])
def test_slack_errors_explain_the_fix(member, settings, monkeypatch, code,
                                      expected_hint):
    """Slack's own error strings are accurate and useless: "channel_not_found" is
    what it says both when the channel does not exist and when the bot was simply
    never invited. The fix is always a specific action in Slack's UI, so the
    message names it. A live token produced exactly this bare error on
    2026-08-04 with nothing pointing at the cause."""
    slack_channel, FakeResponse = _slack_error(code)
    settings.NORA_HOME_SLACK_BOT_TOKEN = "xoxb-test"
    monkeypatch.setattr(slack_channel.requests, "post",
                        lambda *a, **kw: FakeResponse())

    notification = notify(member, title="x", channels=["slack"], sync=True)

    error = notification.deliveries.get().error
    assert code in error, "the raw Slack code should still be there"
    assert expected_hint in error, f"no actionable hint for {code}: {error!r}"


def test_an_unmapped_slack_error_still_reports_the_code(member, settings,
                                                        monkeypatch):
    slack_channel, FakeResponse = _slack_error("ratelimited")
    settings.NORA_HOME_SLACK_BOT_TOKEN = "xoxb-test"
    monkeypatch.setattr(slack_channel.requests, "post",
                        lambda *a, **kw: FakeResponse())

    notification = notify(member, title="x", channels=["slack"], sync=True)

    assert "ratelimited" in notification.deliveries.get().error


def test_alerts_go_to_the_escalation_channel(member, settings, monkeypatch):
    """Severity decides the target: an alert belongs where the house is watching,
    not in someone's DMs alone."""
    import nora_home.notifications.channels.slack as slack_channel

    settings.NORA_HOME_SLACK_BOT_TOKEN = "xoxb-test"
    settings.NORA_HOME_SLACK_ESCALATION_CHANNEL = "#house-alerts"
    seen = {}

    class FakeResponse:
        content = b"{}"

        @staticmethod
        def json():
            return {"ok": True, "ts": "1.0"}

    def capture(url, **kwargs):
        seen.update(kwargs.get("json", {}))
        return FakeResponse()

    monkeypatch.setattr(slack_channel.requests, "post", capture)

    notify(member, title="Smoke alarm", severity=Severity.CRITICAL,
           channels=["slack"], sync=True)

    assert seen["channel"] == "#house-alerts"


def test_a_personal_nudge_goes_to_the_members_dm(make_member, settings, monkeypatch):
    import nora_home.notifications.channels.slack as slack_channel

    settings.NORA_HOME_SLACK_BOT_TOKEN = "xoxb-test"
    person = make_member("kid", slack_user_id="U01ABCDEF")
    seen = {}

    class FakeResponse:
        content = b"{}"

        @staticmethod
        def json():
            return {"ok": True, "ts": "1.0"}

    monkeypatch.setattr(slack_channel.requests, "post",
                        lambda url, **kw: (seen.update(kw.get("json", {})),
                                           FakeResponse())[1])

    notify(person, title="Vitamins", severity=Severity.NUDGE,
           channels=["slack"], sync=True)

    assert seen["channel"] == "U01ABCDEF"


# ── direct messages ──────────────────────────────────────────────────────────

def _fake_slack(monkeypatch, responses):
    """Route each Slack endpoint to a canned response, and record the calls."""
    import nora_home.notifications.channels.slack as slack_channel

    calls = []

    class FakeResponse:
        content = b"{}"

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def post(url, **kwargs):
        calls.append((url, kwargs.get("json", {})))
        for fragment, payload in responses.items():
            if fragment in url:
                return FakeResponse(payload)
        return FakeResponse({"ok": True, "ts": "1.0"})

    monkeypatch.setattr(slack_channel.requests, "post", post)
    return calls


def test_a_dm_opens_a_conversation_before_posting(make_member, settings,
                                                  monkeypatch):
    """chat.postMessage accepts a bare user id, but only once an IM exists —
    otherwise it answers channel_not_found, which looks exactly like a missing
    channel and sends you hunting in the wrong place."""
    settings.NORA_HOME_SLACK_BOT_TOKEN = "xoxb-test"
    person = make_member("kid", slack_user_id="U01ABCDEF")
    calls = _fake_slack(monkeypatch, {
        "conversations.open": {"ok": True, "channel": {"id": "D0FEED"}},
    })

    notify(person, title="Vitamins", channels=["slack"], sync=True)

    urls = [url for url, _ in calls]
    assert any("conversations.open" in u for u in urls), "no DM was opened"
    posted = [body for url, body in calls if "chat.postMessage" in url]
    assert posted[0]["channel"] == "D0FEED", "posted to the user id, not the DM"


def test_the_dm_conversation_is_cached_on_the_member(make_member, settings,
                                                     monkeypatch):
    """One extra API call per person ever, rather than one per notification."""
    settings.NORA_HOME_SLACK_BOT_TOKEN = "xoxb-test"
    person = make_member("kid", slack_user_id="U01ABCDEF")
    _fake_slack(monkeypatch, {
        "conversations.open": {"ok": True, "channel": {"id": "D0FEED"}},
    })

    notify(person, title="Vitamins", channels=["slack"], sync=True)

    person.refresh_from_db()
    assert person.slack_dm_channel == "D0FEED"


def test_a_cached_dm_channel_skips_the_extra_call(make_member, settings,
                                                  monkeypatch):
    settings.NORA_HOME_SLACK_BOT_TOKEN = "xoxb-test"
    person = make_member("kid", slack_user_id="U01ABCDEF",
                         slack_dm_channel="D0CACHED")
    calls = _fake_slack(monkeypatch, {})

    notify(person, title="Vitamins", channels=["slack"], sync=True)

    assert not any("conversations.open" in url for url, _ in calls)
    assert calls[0][1]["channel"] == "D0CACHED"


def test_a_channel_target_is_never_treated_as_a_dm(member, settings, monkeypatch):
    """House-wide messages go to #a-channel; opening a DM for those would be
    both wrong and an extra round trip."""
    settings.NORA_HOME_SLACK_BOT_TOKEN = "xoxb-test"
    settings.NORA_HOME_SLACK_DEFAULT_CHANNEL = "#nora-home"
    calls = _fake_slack(monkeypatch, {})

    notify_house(title="Power cut", channels=["slack"], sync=True)

    assert not any("conversations.open" in url for url, _ in calls)


def test_failing_to_open_a_dm_explains_the_missing_scope(make_member, settings,
                                                         monkeypatch):
    settings.NORA_HOME_SLACK_BOT_TOKEN = "xoxb-test"
    person = make_member("kid", slack_user_id="U01ABCDEF")
    _fake_slack(monkeypatch, {
        "conversations.open": {"ok": False, "error": "missing_scope"},
    })

    notification = notify(person, title="Vitamins", channels=["slack"], sync=True)

    error = notification.deliveries.get().error
    assert "im:write" in error, f"no actionable hint: {error!r}"
