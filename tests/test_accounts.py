"""
The household: roles, quiet hours, and the escalation chain.

Two things here carry real consequence. `HouseMember.save()` forcing the Django
staff/superuser flags from `role` is the *only* gate on /admin/ in a house with
no passwords anywhere — if it stops working, either nobody can administer the
house or everybody can. And `escalation_chain()` decides who gets woken up.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from nora_home.accounts.models import EscalationContact, HouseMember

pytestmark = pytest.mark.django_db


# ── roles and admin access ───────────────────────────────────────────────────

def test_admin_role_grants_django_staff_and_superuser(admin_member):
    """Passwordless admin: role is the gate, so it must imply the flags Django
    itself checks. See CLAUDE.md §4, "Passwordless everywhere"."""
    assert admin_member.is_staff is True
    assert admin_member.is_superuser is True


def test_non_admin_roles_do_not_get_staff_flags(member, adult):
    assert member.is_staff is False
    assert member.is_superuser is False
    assert adult.is_staff is False
    assert adult.is_superuser is False


def test_promoting_someone_to_admin_grants_access_on_save(member):
    member.role = HouseMember.Role.ADMIN
    member.save()

    member.refresh_from_db()
    assert member.is_staff and member.is_superuser


def test_flags_are_forced_on_every_save_not_just_the_first(admin_member):
    """Someone unticking 'superuser' in the admin must not be able to lock the
    house's only administrator out of the admin."""
    admin_member.is_superuser = False
    admin_member.is_staff = False
    admin_member.save()

    admin_member.refresh_from_db()
    assert admin_member.is_staff and admin_member.is_superuser


def test_is_adult_covers_adults_and_admins(member, adult, admin_member):
    assert adult.is_adult is True
    assert admin_member.is_adult is True
    assert member.is_adult is False


def test_name_prefers_the_display_name(make_member):
    person = make_member("nitin", display_name="Nitin")
    assert person.name == "Nitin"


def test_name_falls_back_to_the_username(make_member):
    person = make_member("nitin", display_name="")
    assert person.name == "nitin"


# ── quiet hours ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("hour,expected", [
    (21, False),  # before it starts
    (22, True),   # the moment it starts
    (23, True),
    (2, True),    # across midnight
    (6, True),
    (7, False),   # the moment it ends
    (12, False),
])
def test_quiet_hours_wrapping_midnight(make_member, hour, expected):
    """The default window is 22:00–07:00, which wraps. Getting the wrap wrong
    inverts the whole thing — alerts all night, silence all day."""
    person = make_member(quiet_hours_start=22, quiet_hours_end=7)

    assert person.in_quiet_hours(datetime(2026, 8, 3, hour, 30)) is expected


@pytest.mark.parametrize("hour,expected", [
    (8, False), (9, True), (13, True), (16, False), (17, False),
])
def test_quiet_hours_inside_a_single_day(make_member, hour, expected):
    """A daytime window (a nap, school hours) does not wrap and must not be
    treated as though it does."""
    person = make_member(quiet_hours_start=9, quiet_hours_end=16)

    assert person.in_quiet_hours(datetime(2026, 8, 3, hour, 30)) is expected


def test_quiet_hours_defaults_to_now_when_given_nothing(member):
    assert isinstance(member.in_quiet_hours(), bool)


# ── the escalation chain ─────────────────────────────────────────────────────

def test_an_explicit_chain_is_returned_in_level_order(household):
    chain = household["kid"].escalation_chain()

    assert chain == [household["adult"], household["admin"]]


def test_chain_levels_are_respected_regardless_of_insertion_order(make_member):
    kid = make_member("kid")
    first = make_member("first", role=HouseMember.Role.ADULT)
    second = make_member("second", role=HouseMember.Role.ADULT)
    EscalationContact.objects.create(member=kid, contact=second, level=2)
    EscalationContact.objects.create(member=kid, contact=first, level=1)

    assert kid.escalation_chain() == [first, second]


def test_no_chain_falls_back_to_every_other_adult(make_member):
    """The default has to be safe: someone with nothing configured still gets
    escalated to the grown-ups, rather than to nobody."""
    kid = make_member("kid")
    adult = make_member("parent", role=HouseMember.Role.ADULT)
    admin = make_member("boss", role=HouseMember.Role.ADMIN)
    make_member("sibling")  # another member: not an escalation target

    chain = kid.escalation_chain()

    assert set(chain) == {adult, admin}


def test_the_fallback_chain_never_includes_the_person_themselves(make_member):
    """Telling you that you haven't done your own chore is the nudge, not the
    escalation. An adult escalating to themselves is a dead ladder."""
    adult = make_member("parent", role=HouseMember.Role.ADULT)
    other = make_member("other", role=HouseMember.Role.ADULT)

    assert adult.escalation_chain() == [other]


def test_a_person_cannot_be_listed_twice_on_one_chain(household):
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        EscalationContact.objects.create(
            member=household["kid"], contact=household["adult"], level=3)


def test_deleting_a_contact_does_not_delete_the_member(household):
    EscalationContact.objects.filter(member=household["kid"]).delete()

    assert HouseMember.objects.filter(pk=household["adult"].pk).exists()
    assert household["kid"].escalation_chain(), "should fall back to the adults"
