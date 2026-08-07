"""
Todo, in a real browser.

Story 41 §13.2. The fast suite already proves `api.complete()`, `escalate_due
_instances()` and every `analytics.py` function against a known history — 906
tests worth. None of that runs a line of `todo.js`, and the regression this
suite's own pattern exists for ("Add a widget" 403ing silently for a day, nh-app
.js §2) is exactly the class of bug that lives in the gap between a POST
handler being correct and a browser button actually calling it.
"""

from __future__ import annotations

import pytest

from tests.qa.conftest import measure_text_contrast, open_actions_menu, visit

pytestmark = pytest.mark.qa

QA_TITLE_PREFIX = "QA "


@pytest.fixture(scope="session", autouse=True)
def _sweep_qa_litter_on_exit(browser, house_url):
    """A second, independent guarantee that this file leaves nothing visible on
    the family's real board — belt and suspenders on top of each creation
    test's own `finally:` cleanup, not a fix for it.

    That per-test path was chased as a suspected bug for a while: a fixed-title
    re-run reported "leftover" tasks that a plain `Task.objects.filter(...)`
    query could still see after the suite finished. It turned out to be a
    mistake in the *verification*, not the cleanup — `delete()` (SoftDeleteModel)
    sets `deleted_at` rather than removing the row, and every check that missed
    `.alive()` was counting successfully-deleted history as if it were live
    litter. `Task.objects.alive().filter(title__icontains="QA")` was 0 the whole
    time; the per-test cleanup worked every run.

    Kept anyway, because a suite that creates data on a real family's board
    deserves a session-level guarantee regardless of whether any one test's own
    cleanup path happens to run — the assertion above proves *this session*
    behaved, not that a slower Pi or a future edit always will.

    A fresh page from the session `browser` fixture, not the per-test `page` —
    this must survive to see the very last test's own page/context torn down.
    `/todo/search/?q=` rather than the board: a *done* one-shot task "leaves the
    board entirely" (api.py's own contract) and is not in the archived column
    either, so search — which starts from every alive task, not the open
    board — is the one page that can see all three shapes (open, done,
    archived) in one query."""
    yield
    context = browser.new_context(ignore_https_errors=True, base_url=house_url)
    page = context.new_page()
    try:
        page.goto("/accounts/switch/", wait_until="domcontentloaded")
        buttons = page.locator("form button[type=submit]")
        if buttons.count() == 0:
            return
        buttons.first.click()
        page.wait_for_load_state("load")

        from urllib.parse import quote

        for _ in range(20):  # a generous, finite cap — never loop forever
            page.goto(f"/todo/search/?q={quote(QA_TITLE_PREFIX.strip())}",
                     wait_until="domcontentloaded")
            card = page.locator(".todo-card", has_text=QA_TITLE_PREFIX.strip()).first
            if card.count() == 0:
                break
            href = card.locator(".todo-card__title a").get_attribute("href")
            _delete_task(page, href)
    except Exception:  # noqa: BLE001 — a teardown sweep must never fail the suite
        pass
    finally:
        context.close()


TODO_PAGES = [
    ("board", "/todo/"),
    ("calendar", "/todo/calendar/"),
    ("reporting", "/todo/reporting/"),
    ("search", "/todo/search/"),
    ("labels", "/todo/labels/"),
    ("settings", "/todo/settings/"),
    ("create", "/todo/new/"),
    ("system", "/todo/system/"),
]


# ── the pages, generically ───────────────────────────────────────────────────
# PLATFORM_PAGES in conftest.py never grew Todo's own pages — they sit outside
# /home/ at their own top-level slug (todo/apps.py, Level 2) rather than under
# the platform prefix everything else in that list shares. Covered here
# instead, with the same three checks that list gets.

@pytest.mark.parametrize("name,path", TODO_PAGES, ids=[n for n, _ in TODO_PAGES])
def test_page_loads_without_javascript_errors(signed_in, console_errors, name, path):
    visit(signed_in, path)

    assert not console_errors, (
        f"{name} ({path}) logged browser errors:\n  " + "\n  ".join(console_errors))


@pytest.mark.parametrize("name,path", TODO_PAGES, ids=[n for n, _ in TODO_PAGES])
def test_page_makes_no_failed_requests(signed_in, name, path):
    failures: list[str] = []
    signed_in.on("response", lambda r: failures.append(f"{r.status} {r.url}")
                 if r.status >= 400 and "favicon" not in r.url else None)

    visit(signed_in, path)

    assert not failures, f"{name} ({path}) made failing requests:\n  " + "\n  ".join(failures)


@pytest.mark.parametrize("name,path", TODO_PAGES, ids=[n for n, _ in TODO_PAGES])
def test_page_actually_renders_something(signed_in, name, path):
    visit(signed_in, path)

    body_text = signed_in.locator("body").inner_text().strip()

    assert len(body_text) > 40, f"{name} ({path}) rendered almost nothing: {body_text!r}"


# ── the board's actions survive a reload ─────────────────────────────────────

def test_the_board_renders_its_three_priority_columns(signed_in):
    visit(signed_in, "/todo/")

    assert signed_in.locator(".todo-col--p1").count() == 1
    assert signed_in.locator(".todo-col--p2").count() == 1
    assert signed_in.locator(".todo-col--p3").count() == 1


def test_creating_a_task_puts_it_on_the_board_and_keeps_it(signed_in, console_errors):
    """The pattern test_journeys.py's widget test exists for, aimed at Todo:
    every mutation here goes through NoraHome.post() (todo.js §"the board's
    actions"), the same call whose csrfToken() a JS conflict silently broke
    once already. Clicking through and reloading is the only way that class of
    bug shows up — a 403 that fetch() does not reject on looks identical to
    success until the page is asked again."""
    title = _unique_title("QA journey task")
    visit(signed_in, "/todo/new/")

    signed_in.locator("#id_title").fill(title)
    signed_in.locator('input[name="priority"][value="2"]').check()
    signed_in.locator('.todo-form button[type=submit]').click()
    signed_in.wait_for_load_state("load")

    visit(signed_in, "/todo/")
    href = signed_in.locator(".todo-card", has_text=title) \
                     .locator(".todo-card__title a").get_attribute("href")
    try:
        assert signed_in.locator(f".todo-card__title:has-text('{title}')").count() == 1
    finally:
        _delete_task(signed_in, href)


def _unique_title(base: str) -> str:
    """This suite runs against the family's real Todo board, not a throwaway
    database (conftest.py's own module docstring: "a real browser, against a
    running house") — so a fixed title collides with whatever an earlier run
    left behind. count() == 2 on a re-run is not a product bug, it is two of
    this suite's own cards; the fix is uniqueness and cleanup, not a code
    change. See _delete_task below."""
    import uuid

    return f"{base} {uuid.uuid4().hex[:8]}"


def _create_task(page, *, title: str, priority: str) -> str:
    """A task with `due_on` set to today — without one there is no materialized
    Instance, `task.current` is None, and _card.html renders neither the tick
    nor the archive button at all (only a bare placeholder dot). Found by
    inspecting a created card's outerHTML after the tick locator timed out
    waiting for an element that, correctly, was never rendered.

    Returns the new task's detail URL, captured immediately while it is still
    on the open board — see _delete_task for why re-finding it later is the
    wrong approach."""
    from datetime import date

    visit(page, "/todo/new/")
    page.locator("#id_title").fill(title)
    page.locator(f'input[name="priority"][value="{priority}"]').check()
    page.locator("#id_due_on").fill(str(date.today()))
    page.locator(".todo-form button[type=submit]").click()
    page.wait_for_load_state("load")

    href = page.locator(".todo-card", has_text=title) \
               .locator(".todo-card__title a").get_attribute("href")
    return href


def _delete_task(page, href: str | None):
    """Best-effort cleanup so this suite does not leave permanent litter on a
    real family's board. Not a fixture teardown: a failed assertion must not
    skip it, and a missing href (creation itself failed) must not turn a real
    failure into a second, misleading one — hence the outer try/except.

    Takes the href `_create_task` captured, rather than re-finding the card by
    title afterward — **a completed one-shot task moves `Task.state` to `done`
    and "leaves the board entirely"** (api.py's own contract, quoted in
    test_completing_a_task_... above), so after that action it is on neither
    the open board nor in the archived column, and any card search for it finds
    nothing. First found as leftover "done" tasks silently surviving every
    run — the cleanup never raised, it just had nothing to click on.

    A direct POST through `page.request`, not a UI click: detail.html's delete
    form is a native `confirm()` dialog, and driving that headlessly needs a
    `page.on('dialog', ...)` handler timed exactly around the click — it hung
    for 10+ minutes with no visible error the first time this was tried,
    chasing a browser dialog rather than testing anything Story 41 cares about.
    `page.request` shares the signed-in session's cookies automatically, so this
    is an authenticated POST with the right CSRF token and nothing UI-shaped to
    get stuck on."""
    if not href:
        return
    try:
        uuid = href.rstrip("/").rsplit("/", 1)[-1]
        token = page.evaluate(
            "() => document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? ''")
        page.request.post(f"/todo/t/{uuid}/delete/",
                          headers={"X-CSRFToken": token, "Referer": page.url},
                          timeout=10000)
    except Exception:  # noqa: BLE001 — cleanup must never mask a real failure
        pass


def test_completing_a_task_moves_it_and_the_move_survives_reload(signed_in):
    """Ticks a real card via data-todo-action="complete" — the same click a
    person makes — then reloads, because a fetch() that 403s and gets ignored
    looks identical to a success until you ask the server again."""
    title = _unique_title("QA complete-me task")
    href = _create_task(signed_in, title=title, priority="1")

    visit(signed_in, "/todo/")
    card = signed_in.locator(".todo-card", has_text=title).first
    if card.count() == 0:
        pytest.skip("the created task did not land on the open board — covered "
                    "by the creation test above")
    card.locator("[data-todo-action=complete]").click()
    signed_in.wait_for_timeout(400)

    try:
        visit(signed_in, "/todo/")
        assert signed_in.locator(".todo-card__title", has_text=title).count() == 0, (
            "the completed task is still shown as open after a reload")
    finally:
        # A completed one-shot task moves Task.state to done and "leaves the
        # board entirely" (api.py's own contract) — neither on the open board
        # nor in the archived column, so cleanup has to use the href captured
        # at creation rather than re-finding a card that no longer exists
        # anywhere a search would look. See _delete_task.
        _delete_task(signed_in, href)


def test_archiving_survives_a_reload(signed_in):
    title = _unique_title("QA archive-me task")
    href = _create_task(signed_in, title=title, priority="3")

    visit(signed_in, "/todo/")
    card = signed_in.locator(".todo-card", has_text=title).first
    if card.count() == 0:
        pytest.skip("the created task did not land on the open board")
    card.locator("[data-todo-action=archive]").click()
    signed_in.wait_for_timeout(400)

    try:
        visit(signed_in, "/todo/")
        assert signed_in.locator(".todo-col--archived .todo-card__title",
                                 has_text=title).count() == 1
    finally:
        _delete_task(signed_in, href)


# ── calendar ──────────────────────────────────────────────────────────────────

def test_the_calendar_renders_a_grid_of_days(signed_in):
    visit(signed_in, "/todo/calendar/")

    assert signed_in.locator(".todo-cal__day").count() >= 28, (
        "fewer than a short month's worth of day cells rendered")


# ── reporting: §10's "empty is a sentence, never an axis" ────────────────────

def test_reporting_renders_with_no_could_not_load(signed_in):
    """§10's contract: a chart with nothing to draw renders one line of text,
    not a blank canvas or an error. 'could not load' is what a swallowed
    exception in _reporting_charts() would look like on screen."""
    visit(signed_in, "/todo/reporting/")

    body = signed_in.locator("body").inner_text().lower()
    assert "could not load" not in body
    assert "error" not in body


def test_every_reporting_chart_card_has_content_or_a_sentence(signed_in):
    """Never both empty and contentless — that would be the one state §10
    forbids: an empty box with nothing explaining why.

    Reporting has two card shapes sharing the `.todo-report__card` wrapper —
    eight built from `_chart_card.html` (`.todo-chart`) and five written out by
    hand because each has a different table body (`.todo-table`, per the
    comment above them in reporting.html: "the empty branch has to look
    identical ... or the page reads as two designs"). Checking for content
    directly, rather than for one specific tag, is what keeps this test true of
    both without hardcoding which six are which."""
    visit(signed_in, "/todo/reporting/")

    cards = signed_in.locator(".todo-report__card")
    count = cards.count()
    if count == 0:
        pytest.skip("Reporting has no chart cards on this house")
    for i in range(count):
        card = cards.nth(i)
        has_content = (card.locator(".todo-chart").count() > 0
                       or card.locator(".todo-table").count() > 0)
        has_sentence = card.locator(".todo-empty").count() > 0
        assert has_content or has_sentence, (
            f"reporting card {i} is neither a chart/table nor an empty sentence")


# ── no sideways scroll, the five real sizes ──────────────────────────────────

@pytest.mark.parametrize("width,height,label", [
    (390, 844, "iPhone"),
    (820, 1180, "iPad"),
    (1440, 900, "laptop"),
    (1920, 1080, "the 24-inch wall"),
    (1024, 600, "the 10-inch kiosk"),
])
@pytest.mark.parametrize("name,path", TODO_PAGES, ids=[n for n, _ in TODO_PAGES])
def test_no_horizontal_scroll(signed_in, name, path, width, height, label):
    signed_in.set_viewport_size({"width": width, "height": height})
    visit(signed_in, path)

    overflow = signed_in.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")

    assert overflow <= 1, f"{name} ({path}) scrolls sideways on {label} by {overflow}px"


# ── contrast, measured from pixels, every theme x daypart ───────────────────
# Not axe's color-contrast rule — conftest.py's own comment on why: it
# composites onto a DOM ancestor rather than the living background actually
# painted behind these panes. A contrast bug here was invisible for hours
# because it only showed in daylight, which is why every daypart is checked
# rather than whatever happens to be current when the suite runs.

@pytest.mark.parametrize("daypart", ["dawn", "noon", "dusk", "night"])
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_board_card_titles_clear_aa_contrast(signed_in, theme, daypart):
    visit(signed_in, "/todo/")
    signed_in.evaluate(f"""
        document.documentElement.setAttribute('data-theme', '{theme}');
        document.documentElement.setAttribute('data-daypart', '{daypart}');
    """)
    signed_in.wait_for_timeout(150)

    ratio = measure_text_contrast(signed_in, ".todo-card__title")
    if ratio is None:
        pytest.skip("no task cards on this board to measure")

    assert ratio >= 4.5, (
        f"todo-card__title measures {ratio:.2f}:1 in {theme}/{daypart} — below AA")


@pytest.mark.parametrize("daypart", ["dawn", "noon", "dusk", "night"])
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_reporting_figures_clear_aa_contrast(signed_in, theme, daypart):
    visit(signed_in, "/todo/reporting/")
    signed_in.evaluate(f"""
        document.documentElement.setAttribute('data-theme', '{theme}');
        document.documentElement.setAttribute('data-daypart', '{daypart}');
    """)
    signed_in.wait_for_timeout(150)

    ratio = measure_text_contrast(signed_in, ".todo-figure__value")
    if ratio is None:
        pytest.skip("no figure tiles rendered")

    assert ratio >= 4.5, (
        f"todo-figure__value measures {ratio:.2f}:1 in {theme}/{daypart} — below AA")
