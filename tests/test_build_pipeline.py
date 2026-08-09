"""The front end is built, and the house must not need node to run.

Story 43 put Vite between the source files and the browser. That buys a lot and
introduces one failure mode the old `{% static %}` approach did not have: an
asset can go missing without anything raising until a page is opened on a
screen nobody is looking at. django-vite resolves names out of a manifest, and a
name that is not in it is a stylesheet that silently does not load.

So these tests treat the manifest as the contract. Every entry a template asks
for must be in it, every file it points at must exist on disk, and the whole lot
must be committed — because the Pi never builds and the house has to boot with
no network and no node.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from django.conf import settings

DIST = Path(settings.BASE_DIR) / "static" / "nora_home" / "dist"
MANIFEST = DIST / ".vite" / "manifest.json"
ASSETS = Path(settings.BASE_DIR) / "assets"

# Every asset any template asks Vite for, found the same way a reviewer would:
# by reading them. A new template gets covered without editing this file.
# Both tags, because CSS and JS do not go through the same one — see
# test_stylesheets_are_never_emitted_as_scripts.
VITE_ASSET = re.compile(r"\{%\s*vite_asset(?:_url)?\s+'([^']+)'")


def requested_entries() -> set[str]:
    templates = Path(settings.BASE_DIR) / "templates"
    return {
        name
        for path in templates.rglob("*.html")
        for name in VITE_ASSET.findall(path.read_text(encoding="utf-8"))
    }


@pytest.fixture(scope="module")
def manifest() -> dict:
    if not MANIFEST.exists():
        pytest.fail(
            f"No build output at {MANIFEST}. The house cannot serve a page "
            "without it. Run: ./nora assets")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# ── the contract between templates and the build ─────────────────────────────

def test_every_asset_a_template_asks_for_was_built(manifest):
    """A missing entry is a stylesheet that does not load, with no error."""
    missing = sorted(requested_entries() - set(manifest))

    assert not missing, f"templates ask for entries Vite did not build: {missing}"


def test_every_built_file_actually_exists(manifest):
    """A manifest can name a file that was cleaned away afterwards."""
    for name, entry in manifest.items():
        for relative in [entry["file"], *entry.get("css", [])]:
            assert (DIST / relative).exists(), f"{name} -> {relative} is missing"


def test_every_source_file_is_an_entry(manifest):
    """vite.config.js globs assets/; a file that stops being built is a file
    somebody is still editing for no effect."""
    sources = {
        f"assets/{d}/{p.name}"
        for d, ext in (("css", ".css"), ("js", ".js"))
        for p in (ASSETS / d).glob(f"*{ext}")
    }

    assert sources <= set(manifest), sorted(sources - set(manifest))


def test_stylesheets_are_never_emitted_as_scripts():
    """The bug this exists for: {% vite_asset %} emits a <script type="module">
    for *every* entry, including CSS ones. Vite treats a .css entry as an entry
    like any other, so all six stylesheets went out as module scripts, the
    browser refused them on MIME type, and the house rendered with no styling at
    all. A CSS entry goes through vite_asset_url inside a real <link>.
    """
    offenders = []
    for path in (Path(settings.BASE_DIR) / "templates").rglob("*.html"):
        for name in re.findall(r"\{%\s*vite_asset\s+'([^']+)'", path.read_text(encoding="utf-8")):
            if name.endswith(".css"):
                offenders.append(f"{path.name}: {name}")

    assert not offenders, (
        "these would be served as module scripts and silently ignored: " + str(offenders))


# ── the house runs without node ──────────────────────────────────────────────

def test_the_build_output_is_committed():
    """The Pi never builds and the house must boot offline, so dist/ is source
    as far as git is concerned. Left ignored, a fresh clone serves no CSS."""
    ignored = subprocess.run(
        ["git", "check-ignore", str(MANIFEST)],
        capture_output=True, text=True, cwd=settings.BASE_DIR,
    )

    assert ignored.returncode != 0, "static/nora_home/dist is gitignored"


def test_node_modules_is_not_committed():
    """The other half of the same rule: the output ships, the toolchain does not."""
    tracked = subprocess.run(
        ["git", "ls-files", "node_modules"],
        capture_output=True, text=True, cwd=settings.BASE_DIR,
    ).stdout.strip()

    assert not tracked, "node_modules is tracked"


def test_dev_mode_is_off_by_default():
    """django-vite in dev mode emits script tags pointing at a Vite dev server.
    Defaulting that on under DEBUG would make `runserver` alone serve a house
    with no JavaScript and no error to explain it."""
    assert settings.DJANGO_VITE["default"]["dev_mode"] is False


# ── the surfaces that are easy to forget ─────────────────────────────────────

@pytest.mark.django_db
@pytest.mark.parametrize("url", ["/home/", "/todo/", "/accounts/switch/"])
def test_pages_render_with_resolved_asset_urls(client, admin_member, url):
    """The failure this catches is django-vite raising on a name it cannot
    resolve, which turns a working page into a 500."""
    client.force_login(admin_member)

    response = client.get(url)

    assert response.status_code == 200
    body = response.content.decode()
    assert "/static/nora_home/dist/" in body, "no built asset on the page at all"
    assert "{% vite_asset" not in body


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["displays:kiosk", "displays:wall"])
def test_the_kiosk_and_the_wall_get_their_assets_too(client, admin_member, name):
    """Both screens are templates nobody opens on a laptop, which is exactly why
    a missing asset on them survives review.

    reverse() rather than a literal path, because I wrote the literals from
    memory the first time and both were wrong — a test that 404s proves nothing
    and looks like it proves something.
    """
    from django.urls import reverse

    client.force_login(admin_member)

    response = client.get(reverse(name))

    assert response.status_code == 200
    assert "/static/nora_home/dist/" in response.content.decode()
