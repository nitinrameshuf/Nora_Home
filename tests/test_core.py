"""
Core: the base models every app inherits, the settings store, device tokens,
the audit trail, and the health probes.

These are the pieces that, if they break, break every app at once.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from nora_home.core.api.auth import (
    DeviceTokenAuthentication,
    generate_token,
    hash_token,
)
from nora_home.core.audit import record
from nora_home.core.health import collect_health
from nora_home.core.models import AuditEvent, DeviceToken, HouseSetting
from nora_home.core.settings_store import CACHE_PREFIX, get_setting, invalidate, set_setting

pytestmark = pytest.mark.django_db


# ── settings store ───────────────────────────────────────────────────────────

def test_get_setting_returns_the_default_when_unset():
    assert get_setting("nothing.here", default={"a": 1}) == {"a": 1}


def test_set_then_get_round_trips_a_dict():
    set_setting("displays.wall_power_schedule",
                {"enabled": True, "start_hour": 1, "end_hour": 7})

    assert get_setting("displays.wall_power_schedule")["start_hour"] == 1


def test_set_setting_updates_rather_than_duplicating():
    set_setting("weather.current", {"condition": "rain"})
    set_setting("weather.current", {"condition": "clear"})

    assert HouseSetting.objects.filter(key="weather.current").count() == 1
    assert get_setting("weather.current")["condition"] == "clear"


def test_set_setting_invalidates_the_cache():
    """The store caches for five minutes. Without invalidation, saving the wall
    schedule in Settings would appear to do nothing for the next five minutes —
    which reads to a user as a broken form, not a stale cache."""
    set_setting("k", {"v": 1})
    get_setting("k")  # warm the cache

    set_setting("k", {"v": 2})

    assert get_setting("k") == {"v": 2}


def test_get_setting_actually_uses_the_cache():
    set_setting("cached.key", {"v": "from-db"})
    get_setting("cached.key")

    # Delete the row behind the cache's back; a cached read should survive it.
    HouseSetting.objects.filter(key="cached.key").delete()

    assert get_setting("cached.key") == {"v": "from-db"}


def test_invalidate_forces_the_next_read_to_hit_the_database():
    set_setting("cached.key", {"v": "from-db"})
    get_setting("cached.key")
    HouseSetting.objects.filter(key="cached.key").delete()

    invalidate("cached.key")

    assert get_setting("cached.key", default="gone") == "gone"


def test_falsy_settings_are_not_mistaken_for_missing():
    """A schedule stored as `False`/`0`/`{}` must not silently fall back to the
    default — that is how a disabled feature turns itself back on."""
    set_setting("flag.off", False)
    cache.delete(CACHE_PREFIX + "flag.off")

    assert get_setting("flag.off", default=True) is False


# ── base models ──────────────────────────────────────────────────────────────

def test_timestamps_are_set_on_create(member):
    from nora_home.todo.models import Priority, Task

    task = Task.objects.create(owner=member, priority=Priority.P2, title="x")

    assert task.created_at is not None
    assert task.updated_at is not None


def test_soft_delete_hides_without_destroying(member):
    from nora_home.todo.models import Priority, Task

    task = Task.objects.create(owner=member, priority=Priority.P2, title="Filter")
    task.delete()

    assert Task.objects.filter(pk=task.pk).exists(), "row was really deleted"
    assert task.deleted_at is not None
    assert Task.objects.alive().filter(pk=task.pk).count() == 0
    assert Task.objects.dead().filter(pk=task.pk).count() == 1


def test_soft_deleted_records_can_be_restored(member):
    from nora_home.todo.models import Priority, Task

    task = Task.objects.create(owner=member, priority=Priority.P2, title="Filter")
    task.delete()
    task.restore()

    assert task.deleted_at is None
    assert Task.objects.alive().filter(pk=task.pk).exists()


def test_hard_delete_really_removes_the_row(member):
    from nora_home.todo.models import Priority, Task

    task = Task.objects.create(owner=member, priority=Priority.P2, title="Filter")
    pk = task.pk
    task.hard_delete()

    assert not Task.objects.filter(pk=pk).exists()


def test_queryset_delete_is_also_soft(member):
    from nora_home.todo.models import Priority, Task

    Task.objects.create(owner=member, priority=Priority.P2, title="a")
    Task.objects.create(owner=member, priority=Priority.P2, title="b")

    Task.objects.all().delete()

    assert Task.objects.count() == 2
    assert Task.objects.alive().count() == 0


def test_uuid_model_generates_a_unique_external_id(member):
    from nora_home.todo.models import Priority, Task

    one = Task.objects.create(owner=member, priority=Priority.P2, title="a")
    two = Task.objects.create(owner=member, priority=Priority.P2, title="b")

    assert one.uuid != two.uuid


# ── audit ────────────────────────────────────────────────────────────────────

def test_record_writes_an_audit_row(adult):
    event = record("todo", "escalation.raised", actor=adult,
                   subject="Bins", severity="warning", source="celery", level=2)

    assert event.pk
    assert event.detail == {"level": 2}
    assert event.actor == adult


def test_switching_to_a_member_is_audited(client, member):
    """There is no password in this house, so tapping a name *is* the whole
    authentication story (CLAUDE.md §4) — this row is the only durable record
    that anyone became anyone. Story 40 §12.3."""
    client.post(reverse("accounts:switch_to", args=[member.pk]))

    event = AuditEvent.objects.filter(action="member.switched").first()
    assert event is not None
    assert event.actor == member
    assert event.subject == member.name


def test_switching_records_who_it_was_before(client, member, adult):
    client.force_login(adult)

    client.post(reverse("accounts:switch_to", args=[member.pk]))

    event = AuditEvent.objects.filter(action="member.switched").first()
    assert event.detail["from_member"] == adult.get_username()


def test_changing_the_wall_schedule_records_what_it_was_set_to(client, admin_member):
    """"Why did the wall go dark at six" is only answerable from the log if the
    log says what the hours became, not merely that something changed."""
    client.force_login(admin_member)

    client.post(reverse("core:settings"), {
        "wall_schedule_enabled": "on",
        "wall_schedule_start": "7",
        "wall_schedule_end": "23",
    })

    event = AuditEvent.objects.filter(action="setting.changed").first()
    assert event is not None
    assert event.actor == admin_member
    assert event.detail["start_hour"] == 7
    assert event.detail["end_hour"] == 23
    assert event.detail["enabled"] is True


def test_record_never_raises_even_when_the_write_fails(monkeypatch):
    """Auditing must not be able to break the thing it is auditing."""
    def explode(*args, **kwargs):
        raise RuntimeError("database is on fire")

    monkeypatch.setattr(AuditEvent.objects, "create", explode)

    assert record("todo", "thing.happened") is None


def test_record_tolerates_an_unsaved_actor():
    from nora_home.accounts.models import HouseMember

    event = record("core", "x", actor=HouseMember(username="ghost"))

    assert event is not None
    assert event.actor is None


def test_long_subjects_are_truncated_not_rejected():
    event = record("core", "x", subject="y" * 400)

    assert len(event.subject) == 255


# ── device tokens ────────────────────────────────────────────────────────────

def test_generated_tokens_are_unique_and_prefixed():
    plaintext, prefix, digest = generate_token()

    assert plaintext.startswith("nora_")
    assert plaintext.split("_")[1] == prefix
    assert digest == hash_token(plaintext)
    assert generate_token()[0] != plaintext


def test_a_valid_token_authenticates_as_its_member(rf, adult):
    plaintext, prefix, digest = generate_token()
    DeviceToken.objects.create(name="Robot", token_hash=digest, prefix=prefix,
                               member=adult)

    request = rf.get("/api/", HTTP_AUTHORIZATION=f"Bearer {plaintext}")
    user, token = DeviceTokenAuthentication().authenticate(request)

    assert user == adult
    assert token.name == "Robot"


def test_authenticating_stamps_last_used(rf, adult):
    plaintext, prefix, digest = generate_token()
    token = DeviceToken.objects.create(name="Robot", token_hash=digest,
                                       prefix=prefix, member=adult)

    DeviceTokenAuthentication().authenticate(
        rf.get("/api/", HTTP_AUTHORIZATION=f"Bearer {plaintext}"))

    token.refresh_from_db()
    assert token.last_used_at is not None


def test_a_revoked_token_is_rejected(rf, adult):
    from rest_framework import exceptions

    plaintext, prefix, digest = generate_token()
    DeviceToken.objects.create(name="Old phone", token_hash=digest, prefix=prefix,
                               member=adult, revoked_at=timezone.now())

    with pytest.raises(exceptions.AuthenticationFailed):
        DeviceTokenAuthentication().authenticate(
            rf.get("/api/", HTTP_AUTHORIZATION=f"Bearer {plaintext}"))


def test_a_forged_token_with_a_real_prefix_is_rejected(rf, adult):
    """The prefix is a lookup hint, not a secret. Only the hash may authorise."""
    from rest_framework import exceptions

    _, prefix, digest = generate_token()
    DeviceToken.objects.create(name="Robot", token_hash=digest, prefix=prefix,
                               member=adult)

    with pytest.raises(exceptions.AuthenticationFailed):
        DeviceTokenAuthentication().authenticate(
            rf.get("/api/", HTTP_AUTHORIZATION=f"Bearer nora_{prefix}_wrongsecret"))


def test_a_token_bound_to_nobody_is_rejected(rf):
    from rest_framework import exceptions

    plaintext, prefix, digest = generate_token()
    DeviceToken.objects.create(name="Orphan", token_hash=digest, prefix=prefix,
                               member=None)

    with pytest.raises(exceptions.AuthenticationFailed):
        DeviceTokenAuthentication().authenticate(
            rf.get("/api/", HTTP_AUTHORIZATION=f"Bearer {plaintext}"))


def test_requests_without_a_bearer_header_are_passed_through(rf):
    """Returning None hands off to session auth — the browser path. Raising here
    would lock every logged-in family member out of the API."""
    assert DeviceTokenAuthentication().authenticate(rf.get("/api/")) is None
    assert DeviceTokenAuthentication().authenticate(
        rf.get("/api/", HTTP_AUTHORIZATION="Bearer sometheirtoken")) is None


def test_a_malformed_token_is_rejected(rf):
    from rest_framework import exceptions

    with pytest.raises(exceptions.AuthenticationFailed):
        DeviceTokenAuthentication().authenticate(
            rf.get("/api/", HTTP_AUTHORIZATION="Bearer nora_onlytwoparts"))


def test_device_token_is_active_tracks_revocation(adult):
    token = DeviceToken.objects.create(name="x", token_hash="h", prefix="p",
                                       member=adult)
    assert token.is_active is True

    token.revoked_at = timezone.now()
    assert token.is_active is False


# ── health ───────────────────────────────────────────────────────────────────

def test_collect_health_reports_every_probe():
    health = collect_health()

    assert set(health["services"]) == {
        "database", "redis", "rabbitmq", "mongo", "object_storage", "disk",
        "cpu_temperature",
    }


def test_the_database_probe_passes_against_the_test_database():
    assert collect_health()["services"]["database"]["status"] == "ok"


def test_a_probe_that_raises_is_reported_as_down_not_propagated(monkeypatch):
    """systemd watches /health. A probe that blows up must not take the endpoint
    with it, or a dead Mongo reads as a dead house."""
    import nora_home.core.health as health_module

    def explode():
        raise RuntimeError("boom")

    monkeypatch.setitem(health_module.PROBES, "mongo", explode)

    health = collect_health()

    assert health["services"]["mongo"]["status"] == "down"
    assert "mongo" in health["degraded"]


def test_a_non_critical_service_being_down_leaves_the_house_healthy(monkeypatch):
    """"A dead Mongo is degraded, not down" — the rule from CLAUDE.md §6."""
    import nora_home.core.health as health_module

    monkeypatch.setitem(health_module.PROBES, "mongo", lambda: {"status": "down"})

    health = collect_health()

    assert health["healthy"] is True
    assert "mongo" in health["degraded"]


def test_a_critical_service_being_down_makes_the_house_unhealthy(monkeypatch):
    import nora_home.core.health as health_module

    monkeypatch.setitem(health_module.PROBES, "database", lambda: {"status": "down"})

    assert collect_health()["healthy"] is False


# ── the console rail's vitals (Story 48) ─────────────────────────────────────

def test_the_rail_only_shows_vitals_the_house_actually_measures():
    """The mockup's rail drew six vitals — CPU, MEM, TEMP, FAN, LOAD, UP — and
    its own comment admits only temperature and disk are collected. Story 52
    adds the rest as telemetry series. Until then a rail showing a plausible
    CPU number would be worse than a short rail, because it would be believed.
    """
    from nora_home.core.vitals import rail_vitals

    keys = {vital["key"] for vital in rail_vitals()}

    assert keys <= {"TEMP", "DISK"}, f"invented vitals: {keys - {'TEMP', 'DISK'}}"


def test_the_rail_never_calls_the_full_health_sweep(monkeypatch):
    """This runs in a context processor on every page in the house.
    collect_health() additionally opens TCP connections to redis, rabbitmq,
    mongo and MinIO with a 2s timeout each — eight seconds of socket work per
    page render is what makes a wall feel broken."""
    import nora_home.core.health as health
    from nora_home.core.vitals import rail_vitals

    def explode():
        raise AssertionError("rail_vitals() must not call collect_health()")

    monkeypatch.setattr(health, "collect_health", explode)

    rail_vitals()


def test_a_failed_probe_costs_that_vital_not_the_page(monkeypatch):
    """Chrome on every page: a probe that raises must drop its own line and
    leave the rest of the rail standing (CLAUDE.md §6, failures degrade).

    Both halves are asserted deliberately. There is no thermal zone on a
    laptop, so "TEMP is absent" is true here whatever the code does — the
    working case has to be forced first or this test proves nothing off the
    Pi, which is exactly where it usually runs.
    """
    import nora_home.core.health as health
    from nora_home.core.vitals import rail_vitals

    monkeypatch.setattr(health, "check_cpu_temperature",
                        lambda: {"status": "ok", "celsius": 50.0})
    assert "TEMP" in {v["key"] for v in rail_vitals()}

    def explode():
        raise OSError("thermal zone went away")

    monkeypatch.setattr(health, "check_cpu_temperature", explode)

    keys = {vital["key"] for vital in rail_vitals()}

    assert "TEMP" not in keys
    assert "DISK" in keys, "one broken probe took the whole rail down with it"


def test_every_bar_is_a_percentage(monkeypatch):
    """The bar is rendered straight into `width: N%`, so a value outside 0-100
    would overflow its own track rather than clamp."""
    import nora_home.core.health as health
    from nora_home.core.vitals import rail_vitals

    monkeypatch.setattr(health, "check_cpu_temperature",
                        lambda: {"status": "critical", "celsius": 400.0})
    monkeypatch.setattr(health, "check_disk",
                        lambda: {"status": "ok", "percent_used": -20.0, "free_gb": 1})

    for vital in rail_vitals():
        assert 0 <= vital["bar"] <= 100, f"{vital['key']} bar is {vital['bar']}"


def test_a_hot_pi_is_marked_warm(monkeypatch):
    import nora_home.core.health as health
    from nora_home.core.vitals import rail_vitals

    monkeypatch.setattr(health, "check_cpu_temperature",
                        lambda: {"status": "warning", "celsius": 75.0})

    temp = [v for v in rail_vitals() if v["key"] == "TEMP"][0]

    assert temp["warm"] is True


def test_signing_out_costs_nothing_to_compute(rf):
    """No vitals for an anonymous request — the login page has no rail to put
    them in, and probing the machine for a page that cannot show them is pure
    waste on every unauthenticated hit."""
    from django.contrib.auth.models import AnonymousUser

    from nora_home.core.context_processors import house

    request = rf.get("/home/")
    request.user = AnonymousUser()

    assert house(request)["nh_vitals"] == []
