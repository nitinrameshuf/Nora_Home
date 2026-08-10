"""
Every page in the house, actually requested.

This is the cheapest test in the suite per bug caught. Most of what breaks a
Django page — a renamed URL name in a template, a context key a template reads
but the view stopped setting, a multi-line `{# #}` comment rendering as visible
text — is invisible to unit tests and to `manage.py check`, and only shows up
when someone loads the page. On the wall display, "someone" might be nobody for
a day.

It also asserts the passwordless-access model in both directions: everything
needs *a* signed-in member, and nothing needs a password.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from nora_home.accounts.models import HouseMember
from nora_home.core.registry import registered_apps

pytestmark = pytest.mark.django_db


# Every platform page a person can reach, by URL name. core:house_log is
# deliberately not here — Story 47 turned it into a redirect (see below),
# not a page that renders 200 on its own.
PLATFORM_PAGES = [
    "core:dashboard",
    "core:system_status",
    "core:settings",
    "accounts:household",
    "notifications:inbox",
    "telemetry:index",
    "integrations:index",
    "ai:console",
    "todo:board",
    "todo:calendar",
    "todo:search",
    "todo:labels",
    "todo:create",
]


@pytest.mark.parametrize("url_name", PLATFORM_PAGES)
def test_every_platform_page_renders(client, admin_member, url_name):
    client.force_login(admin_member)

    response = client.get(reverse(url_name))

    assert response.status_code == 200, f"{url_name} returned {response.status_code}"


@pytest.mark.parametrize("url_name", PLATFORM_PAGES)
def test_no_page_leaks_an_unrendered_template_tag(client, admin_member, url_name):
    """Django's `{# #}` is single-line only; a multi-line one renders as visible
    text on the page. That exact bug has shipped in this project before."""
    client.force_login(admin_member)

    body = client.get(reverse(url_name)).content.decode()

    assert "{%" not in body, f"{url_name} has an unrendered template tag"
    assert "{{" not in body, f"{url_name} has an unrendered variable"


@pytest.mark.parametrize("url_name", PLATFORM_PAGES)
def test_every_platform_page_requires_a_member(client, url_name):
    """No passwords anywhere, but never anonymous either — the switcher is the
    front door, and it must be the only one."""
    response = client.get(reverse(url_name))

    assert response.status_code == 302
    assert "/accounts/" in response.headers["Location"]


def test_every_house_app_page_renders(client, admin_member):
    """A house app whose page 500s is the platform's problem, not just the
    app's — the Apps directory links to it."""
    client.force_login(admin_member)

    for meta in registered_apps():
        if meta.is_platform or not meta.has_page:
            continue
        response = client.get(meta.url)
        assert response.status_code == 200, (
            f"{meta.slug} at {meta.url} returned {response.status_code}")


def test_the_bare_domain_lands_on_the_home_dashboard(client, adult):
    client.force_login(adult)

    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("core:dashboard")


def test_the_health_endpoint_answers(client):
    """systemd and the deploy script watch this; it must not need a login."""
    response = client.get("/home/health/")

    assert response.status_code in (200, 503)
    assert "healthy" in response.json()


# ── the passwordless switcher ────────────────────────────────────────────────

def test_the_switcher_lists_the_household(client, household):
    response = client.get(reverse("accounts:switch_picker"))

    assert response.status_code == 200
    for person in household.values():
        assert person.name.encode() in response.content


def test_the_switcher_is_reachable_without_signing_in(client, household):
    assert client.get(reverse("accounts:switch_picker")).status_code == 200


def test_tapping_a_name_signs_you_in_with_no_password(client, adult):
    response = client.post(reverse("accounts:switch_to", args=[adult.pk]))

    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(adult.pk)


def test_switching_requires_post(client, adult):
    """A GET would mean any link — or any prefetching browser — could change who
    the house thinks you are."""
    assert client.get(reverse("accounts:switch_to", args=[adult.pk])).status_code == 405


def test_you_cannot_become_a_deactivated_member(client, adult):
    adult.is_active = False
    adult.save()

    assert client.post(reverse("accounts:switch_to", args=[adult.pk])).status_code == 404


def test_everyone_scope_shows_the_combined_view(client, household):
    response = client.post(reverse("accounts:switch_to_everyone"))

    assert response.status_code == 302
    assert client.session["nh_view_scope"] == "all"


def test_switching_to_a_person_leaves_everyone_scope(client, household):
    client.post(reverse("accounts:switch_to_everyone"))

    client.post(reverse("accounts:switch_to", args=[household["kid"].pk]))

    assert client.session["nh_view_scope"] == "self"


def test_wall_scope_is_reachable_from_a_phone_or_laptop(client, household):
    """§11.2: the 24" has no input devices, so its layout is arranged from
    here — anyone's own browser, switched into this scope."""
    response = client.post(reverse("accounts:switch_to_wall"))

    assert response.status_code == 302
    assert client.session["nh_view_scope"] == "wall"


def test_switching_to_a_person_leaves_wall_scope_too(client, household):
    client.post(reverse("accounts:switch_to_wall"))

    client.post(reverse("accounts:switch_to", args=[household["kid"].pk]))

    assert client.session["nh_view_scope"] == "self"


def test_wall_scope_needs_a_post(client):
    assert client.get(reverse("accounts:switch_to_wall")).status_code == 405


def test_a_crafted_next_parameter_cannot_bounce_you_off_the_house(client, adult):
    """The switcher takes ?next=. Without the host check, a link mailed to a
    family member could log them in and then land them on an attacker's page."""
    response = client.post(reverse("accounts:switch_to", args=[adult.pk]),
                           {"next": "https://evil.invalid/steal"})

    assert "evil.invalid" not in response.headers["Location"]


def test_a_local_next_parameter_is_honoured(client, adult):
    response = client.post(reverse("accounts:switch_to", args=[adult.pk]),
                           {"next": "/home/settings/"})

    assert response.headers["Location"] == "/home/settings/"


def test_signing_out_just_asks_again(client, adult):
    client.force_login(adult)

    response = client.get(reverse("accounts:logout"))

    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


def test_the_profile_page_redirects_into_settings(client, adult):
    """Folded into Settings; kept as a redirect so old links still land."""
    client.force_login(adult)

    response = client.get(reverse("accounts:profile"))

    assert response.headers["Location"] == reverse("core:settings")


# ── admin access follows role, with no password ──────────────────────────────

def test_an_admin_member_reaches_the_django_admin(client, admin_member):
    client.force_login(admin_member)

    assert client.get("/admin/").status_code == 200


def test_a_non_admin_member_does_not(client, member):
    client.force_login(member)

    response = client.get("/admin/")

    assert response.status_code == 302


# ── the settings page ────────────────────────────────────────────────────────

def test_the_settings_page_shows_both_screens(client, adult, wall_display,
                                              kiosk_display):
    client.force_login(adult)

    body = client.get(reverse("core:settings")).content.decode()

    assert "Wall" in body
    assert "Kiosk" in body


def test_saving_the_overnight_schedule_persists_it(client, adult):
    from nora_home.core.settings_store import get_setting

    client.force_login(adult)

    client.post(reverse("core:settings"), {
        "wall_schedule_enabled": "on",
        "wall_schedule_start": "1",
        "wall_schedule_end": "7",
    })

    schedule = get_setting("displays.wall_power_schedule")
    assert schedule["enabled"] is True
    assert schedule["start_hour"] == 1
    assert schedule["end_hour"] == 7


def test_unticking_the_schedule_disables_it(client, adult):
    from nora_home.core.settings_store import get_setting

    client.force_login(adult)
    client.post(reverse("core:settings"), {"wall_schedule_enabled": "on",
                                           "wall_schedule_start": "1",
                                           "wall_schedule_end": "7"})

    client.post(reverse("core:settings"), {"wall_schedule_start": "1",
                                           "wall_schedule_end": "7"})

    assert get_setting("displays.wall_power_schedule")["enabled"] is False


# ── the ⌘K palette tells the truth (Story 47 deleted the Apps directory) ─────

def test_the_palette_lists_home_and_every_nav_app(client, admin_member):
    """Home is the base app; the only things called apps are the four
    registered apps with nav=True. A house app leaking in unnoticed, or a
    platform page silently dropping out, would both be bugs the search box
    would otherwise hide."""
    from nora_home.core.registry import palette_destinations

    client.force_login(admin_member)

    titles = [d["title"] for d in palette_destinations("admin")]
    for expected in ("Home", "System", "Settings", "Alerts", "Measurements",
                     "Integrations"):
        assert expected in titles, f"{expected} is missing from the palette"
    # Todo declares sections, so its own bare title never appears — "Todo —
    # Tasks" etc. does instead. See palette_destinations()'s own docstring.
    assert any(t.startswith("Todo") for t in titles), "no Todo destination in the palette"


def test_every_palette_destination_actually_resolves(client, admin_member):
    """The palette must never send someone somewhere that 404s."""
    from nora_home.core.registry import palette_destinations

    client.force_login(admin_member)

    for dest in palette_destinations("admin"):
        assert client.get(dest["url"]).status_code == 200, f"{dest['url']} is broken"


def test_the_palette_is_empty_when_signed_out(rf):
    """nora_home.core.context_processors.house() skips palette_destinations()
    entirely for an unauthenticated request, rather than computing it at the
    default role — nobody signed out should see a member's own nav baked into
    a page's HTML."""
    from nora_home.core.context_processors import house

    request = rf.get("/home/")
    request.user = AnonymousUser()

    assert house(request)["nh_palette"] == []


# ── the old House log URL still lands somewhere useful ───────────────────────

def test_the_old_log_url_redirects_to_system(client, admin_member):
    client.force_login(admin_member)

    response = client.get("/home/log/")

    assert response.status_code == 302
    assert response["Location"] == reverse("core:system_status")


def test_the_old_log_url_keeps_its_query_string(client, admin_member):
    """A filtered log view was a URL someone could send to somebody else —
    that has to keep working through the redirect, not just the bare page."""
    client.force_login(admin_member)

    response = client.get("/home/log/", {"days": "30", "severity": "warning"})

    assert response.status_code == 302
    assert response["Location"] == reverse("core:system_status") + "?days=30&severity=warning"


# ── error pages ──────────────────────────────────────────────────────────────

def test_a_missing_page_renders_the_houses_own_404(client, adult):
    client.force_login(adult)

    response = client.get("/home/definitely-not-a-page/")

    assert response.status_code == 404
