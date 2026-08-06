"""
Analytics, tone and the Reporting page (docs/Main_App/subsystems/todo.md §10,
and §13's rules about how the numbers are allowed to be computed).

Instances are written directly here rather than driven through `api.complete()`
— the same choice `daily_with_history` makes in test_todo.py. Nearly every
statistic in this module is bucketed by calendar day, so a test has to be able
to say "this was finished 40 days ago at 09:00" exactly; going through the real
transition would put everything at `timezone.now()` and there would be no
history to measure. The transitions themselves are tested in test_todo.py.

Three properties get tested harder than the rest, because they are the ones the
design doc says are worth getting wrong quietly:

* **Effort splits across assignees, never multiplies** (§4a). A 60-minute task
  shared three ways is 20 minutes each; the opposite tells three people they
  each have a full day of what is really an hour of house work.
* **"No data" is not zero** (analytics.py rule 2). `None` means nothing was
  due; `0` means things were due and none happened. Rendering the first as the
  second accuses somebody of failing a week the house asked nothing of them.
* **Nothing is cached** (§13). Every number is recomputed from history on read,
  so a retroactive edit is visible immediately.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from nora_home.todo import analytics, tone
from nora_home.todo.models import (
    ChangeEvent,
    Instance,
    InstanceOutcome,
    Label,
    Priority,
    Task,
    TaskState,
    TodoPreference,
    Tone,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def make_task(member):
    def _make(**kwargs):
        kwargs.setdefault("title", "A thing")
        kwargs.setdefault("owner", member)
        kwargs.setdefault("priority", Priority.P2)
        return Task.objects.create(**kwargs)

    return _make


@pytest.fixture
def done_on(make_task):
    """One finished occasion, `days_ago` days back at a fixed local hour.

    The hour is pinned so a suite run just after midnight cannot push a
    completion into the previous local day and quietly change which bucket
    every day-based assertion lands in.
    """
    def _make(days_ago: int, *, task=None, hour: int = 9, minutes=None, **kwargs):
        task = task or make_task(**kwargs)
        when = timezone.localtime(timezone.now()).replace(
            hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
        return Instance.objects.create(
            task=task, due_at=when, outcome=InstanceOutcome.DONE,
            completed_at=when, actual_minutes=minutes)

    return _make


@pytest.fixture
def pending(make_task):
    def _make(*, days_ahead: int = 1, task=None, **kwargs):
        task = task or make_task(**kwargs)
        return Instance.objects.create(
            task=task, due_at=timezone.now() + timedelta(days=days_ahead))

    return _make


def people(member):
    return [member]


# ── scoping ──────────────────────────────────────────────────────────────────

def test_a_deleted_task_leaves_the_numbers(make_task, member):
    """Soft-deleted is gone. Archived is not — "not now" is a state a chart
    should still be able to show."""
    kept = make_task(title="Kept")
    gone = make_task(title="Gone")
    gone.deleted_at = timezone.now()
    gone.save()

    titles = {task.title for task in analytics.tasks_of(people(member))}

    assert titles == {"Kept"}
    assert kept.title in titles


def test_an_archived_task_stays_in_the_numbers(make_task, member):
    make_task(title="Parked", state=TaskState.ARCHIVED)

    assert analytics.tasks_of(people(member)).count() == 1


def test_instances_of_windows_on_the_due_moment(done_on, member):
    done_on(2)
    done_on(40)

    recent = analytics.instances_of(
        people(member), since=timezone.now() - timedelta(days=10))

    assert recent.count() == 1


# ── "no data" is not zero ────────────────────────────────────────────────────

def test_throughput_with_no_history_is_none_not_zero(member):
    assert analytics.typical_throughput(people(member))["median"] is None


def test_cycle_times_with_no_history_are_none_not_zero(member):
    result = analytics.cycle_times(people(member))

    assert result["created_to_done_days"] is None
    assert result["count"] == 0


def test_first_touch_with_no_history_is_none_not_zero(member):
    assert analytics.time_to_first_touch(people(member))["median_days"] is None


def test_estimate_accuracy_with_no_history_is_none_not_zero(member):
    assert analytics.estimate_accuracy(people(member))["ratio"] is None


def test_priority_share_is_none_when_nothing_is_open(member):
    """A share of 0% would claim a measured emptiness; there is nothing to take
    a percentage of at all."""
    rows = analytics.priority_distribution(people(member))

    assert all(row["share"] is None for row in rows)
    assert all(row["count"] == 0 for row in rows)


# ── realistic load ───────────────────────────────────────────────────────────

def test_throughput_counts_empty_days_as_real_zeros(done_on, member):
    """Five things on one day out of ninety is a median of 0, not 5. Dropping
    the empty days would set exactly the unreachable target §10 avoids."""
    task = done_on(3).task
    for _ in range(4):
        done_on(3, task=task)

    result = analytics.typical_throughput(people(member), days=90)

    assert result["total"] == 5
    assert result["median"] == 0


def test_throughput_reports_a_median_not_a_mean(done_on, make_task, member):
    """One burst of twenty must not become "you typically do 2 a day"."""
    for day in range(1, 11):
        done_on(day)
    burst = make_task(title="Burst day")
    for _ in range(20):
        done_on(1, task=burst)

    result = analytics.typical_throughput(people(member), days=10)

    assert result["total"] == 30
    assert result["median"] <= 2


def test_open_load_counts_what_is_open_and_what_is_late(pending, make_task, member):
    late_task = make_task(title="Late")
    Instance.objects.create(task=late_task, due_at=timezone.now() - timedelta(hours=2))
    pending(days_ahead=3)

    load = analytics.open_load(people(member))

    assert load["count"] == 2
    assert load["overdue"] == 1


def test_open_load_splits_shared_effort_instead_of_multiplying(
        make_task, make_member, member):
    """§4a, and the single most consequential arithmetic decision in the app:
    a 60-minute task shared three ways is 20 minutes each. Counting it in full
    for everyone would tell three people they each have an hour of what is one
    hour of house work between them."""
    other, third = make_member("bob"), make_member("carol")
    task = make_task(title="Shared", planned_minutes=60)
    task.assignees.set([member, other, third])
    Instance.objects.create(task=task, due_at=timezone.now() + timedelta(days=1))

    assert analytics.open_load(people(member))["minutes"] == 20


def test_open_load_separates_no_estimate_from_no_work(make_task, member):
    """Treating "nobody estimated it" as zero minutes makes a full day look
    empty, which is the load calculation being confidently wrong."""
    estimated = make_task(title="Estimated", planned_minutes=30)
    Instance.objects.create(task=estimated, due_at=timezone.now() + timedelta(days=1))
    guessed = make_task(title="No idea")
    Instance.objects.create(task=guessed, due_at=timezone.now() + timedelta(days=1))

    load = analytics.open_load(people(member))

    assert load["minutes"] == 30
    assert load["unestimated"] == 1
    assert load["count"] == 2


def test_open_load_ignores_instances_of_archived_tasks(make_task, member):
    parked = make_task(title="Parked", state=TaskState.ARCHIVED)
    Instance.objects.create(task=parked, due_at=timezone.now() + timedelta(days=1))

    assert analytics.open_load(people(member))["count"] == 0


# ── what counts as done ──────────────────────────────────────────────────────

def test_awaiting_approval_is_not_a_completion(make_task, member):
    """§4a is explicit: it "does not count as a completion in Reporting until
    approved". It has left the board, but the work is not confirmed."""
    task = make_task(title="Needs a yes")
    Instance.objects.create(task=task, due_at=timezone.now() - timedelta(days=1),
                            outcome=InstanceOutcome.AWAITING_APPROVAL,
                            completed_at=timezone.now() - timedelta(days=1))

    assert analytics.typical_throughput(people(member))["total"] == 0
    assert analytics.streak(people(member))["ratio_done"] == 0


def test_a_skip_is_not_folded_into_completions(make_task, member):
    task = make_task(title="Deliberately not today")
    Instance.objects.create(task=task, due_at=timezone.now() - timedelta(days=1),
                            outcome=InstanceOutcome.SKIPPED)

    assert analytics.typical_throughput(people(member))["total"] == 0


# ── deferral ─────────────────────────────────────────────────────────────────

def _moved(task, frm, to):
    return ChangeEvent.objects.create(task=task, field="due_on",
                                      from_value=frm, to_value=to)


def test_deferral_is_read_from_the_change_trail(make_task, member):
    task = make_task(title="Slides")
    label = Label.objects.create(name="garden")
    task.labels.set([label])
    _moved(task, "2026-08-01", "2026-08-03")
    _moved(task, "2026-08-03", "2026-08-07")

    rows = analytics.deferral_by_label(people(member))

    assert rows == [{"label": "garden", "moves": 2, "median_days": 3}]


def test_an_unlabelled_task_is_reported_not_dropped(make_task, member):
    """"The things I never got round to labelling" is frequently the answer."""
    _moved(make_task(title="Nameless"), "2026-08-01", "2026-08-02")

    rows = analytics.deferral_by_label(people(member))

    assert rows[0]["label"] is None


def test_deferral_uses_a_median_so_one_outlier_cannot_dominate(make_task, member):
    task = make_task(title="Slides")
    task.labels.set([Label.objects.create(name="garden")])
    _moved(task, "2026-08-01", "2026-08-02")
    _moved(task, "2026-08-02", "2026-08-03")
    _moved(task, "2026-08-03", "2027-08-03")  # pushed a year

    assert analytics.deferral_by_label(people(member))[0]["median_days"] == 1


def test_a_move_with_no_measurable_distance_is_none_not_zero(make_task, member):
    """Gaining or losing a due date is a real move, but not by a number of
    days — and zero would read as "rescheduled to the same day"."""
    task = make_task(title="Gained a date")
    _moved(task, "", "2026-08-02")

    rows = analytics.deferral_by_label(people(member))

    assert rows[0]["moves"] == 1
    assert rows[0]["median_days"] is None


def test_an_unparseable_date_change_does_not_raise(make_task, member):
    _moved(make_task(title="Odd"), "not-a-date", "also-not")

    assert analytics.deferral_by_label(people(member))[0]["median_days"] is None


# ── time to first touch, cycle time ──────────────────────────────────────────

def test_first_touch_measures_to_the_earliest_completion(make_task, member):
    task = make_task(title="Sat a while")
    task.created_at = timezone.now() - timedelta(days=10)
    task.save()
    for days_ago in (2, 6):
        when = timezone.now() - timedelta(days=days_ago)
        Instance.objects.create(task=task, due_at=when,
                                outcome=InstanceOutcome.DONE, completed_at=when)

    result = analytics.time_to_first_touch(people(member))

    assert result["tasks"] == 1
    assert result["median_days"] == pytest.approx(4.0, abs=0.2)


def test_cycle_time_stays_signed_so_early_reads_as_early(make_task, member):
    """Clamping to zero would erase the difference between "always just in
    time" and "usually a day ahead", which is most of what the number is for."""
    task = make_task(title="Ahead of it")
    due = timezone.now() - timedelta(days=5)
    Instance.objects.create(task=task, due_at=due, outcome=InstanceOutcome.DONE,
                            completed_at=due - timedelta(days=2))

    assert analytics.cycle_times(people(member))["due_to_done_days"] < 0


# ── priorities, aging ────────────────────────────────────────────────────────

def test_priority_share_is_a_percentage_not_a_ratio(make_task, member):
    """§10's Visual discipline: "percentages are percentages". A 0-to-1 ratio
    axis is one of the six failures this page exists not to repeat."""
    make_task(title="One", priority=Priority.P1)
    for n in range(3):
        make_task(title=f"Two {n}", priority=Priority.P2)

    rows = {row["priority"]: row["share"]
            for row in analytics.priority_distribution(people(member))}

    assert rows[Priority.P1] == 25.0
    assert rows[Priority.P2] == 75.0


def test_aging_returns_the_uuid_the_archive_button_needs(make_task, member):
    """§10 pairs this chart with "one-tap archive beside each"."""
    task = make_task(title="Old")

    row = analytics.aging_open_items(people(member))[0]

    assert row["uuid"] == str(task.uuid)
    assert row["age_days"] == 0


def test_aging_buckets_open_work_by_how_long_it_has_sat(make_task, member):
    old = make_task(title="Ancient", priority=Priority.P1)
    Task.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=120))
    make_task(title="Fresh", priority=Priority.P1)

    buckets = {row["priority"]: row["buckets"]
               for row in analytics.aging_by_priority(people(member))}

    assert buckets[Priority.P1]["> 3 months"] == 1
    assert buckets[Priority.P1]["< 1 week"] == 1


# ── evidence of agency, recovery ─────────────────────────────────────────────

def test_recent_completions_are_newest_first(done_on, make_task, member):
    done_on(5, task=make_task(title="Older"))
    done_on(1, task=make_task(title="Newer"))

    assert [row["title"] for row in analytics.recent_completions(people(member))] == [
        "Newer", "Older"]


def test_a_gap_and_a_return_is_recorded_as_a_recovery(done_on, member):
    """Reported as a positive — counting restarts is the whole point, because
    a counter that resets to zero is an argument for never restarting."""
    done_on(20)
    done_on(2)

    found = analytics.recoveries(people(member))

    assert len(found) == 1
    assert found[0]["gap_days"] == 18


def test_working_steadily_produces_no_recoveries(done_on, member):
    for day in range(1, 6):
        done_on(day)

    assert analytics.recoveries(people(member)) == []


# ── cumulative flow, histogram, heatmap, rhythm ──────────────────────────────

def test_cumulative_flow_includes_today(done_on, member):
    """The bug `_day_window()` was written to fix: a naive `now - N×24h` window
    starts partway through the oldest day and never reaches today, so the one
    day someone opened the page to look at was always missing."""
    done_on(0, hour=1)

    flow = analytics.cumulative_flow(people(member), days=7)

    assert flow["days"][-1] == timezone.localdate().isoformat()
    assert flow["completed"][-1] == 1


def test_cumulative_flow_accumulates_rather_than_resetting(done_on, member):
    for day in (1, 2, 3):
        done_on(day)

    flow = analytics.cumulative_flow(people(member), days=7)

    assert flow["completed"] == sorted(flow["completed"])
    assert flow["completed"][-1] == 3


def test_cumulative_flow_with_nothing_at_all_draws_no_axis(member):
    """"Empty is a sentence, never an axis" starts here: the data layer says
    there is nothing, so the view has something unambiguous to branch on."""
    assert analytics.cumulative_flow(people(member)) == {
        "days": [], "arrived": [], "completed": []}


def test_the_histogram_is_a_distribution_not_an_average(done_on, make_task, member):
    task = make_task(title="Busy day")
    for _ in range(3):
        done_on(1, task=task)

    result = analytics.throughput_histogram(people(member), days=5)

    assert result["buckets"] == [0, 1, 2, 3]
    assert result["counts"][3] == 1   # one day had three
    assert result["counts"][0] == 4   # the other four had none


def test_the_heatmap_omits_empty_days_rather_than_zeroing_them(done_on, member):
    done_on(1)

    cells = analytics.completion_heatmap(people(member))

    assert len(cells) == 1
    assert cells[0][1] == 1


def test_rhythm_counts_by_local_hour_and_weekday(done_on, member):
    done_on(1, hour=14)

    rhythm = analytics.completion_rhythm(people(member))

    assert rhythm["total"] == 1
    assert rhythm["hours"][14] == 1
    assert sum(rhythm["weekdays"]) == 1


# ── labels, estimates, streaks ───────────────────────────────────────────────

def test_label_distribution_counts_occasions_not_tasks(done_on, make_task, member):
    """A daily habit and a one-off errand are weighted by how much they were
    really done, not by how many rows they occupy."""
    habit = make_task(title="Daily")
    habit.labels.set([Label.objects.create(name="health")])
    for day in (1, 2, 3):
        done_on(day, task=habit)
    errand = make_task(title="Once")
    errand.labels.set([Label.objects.create(name="admin")])
    done_on(1, task=errand)

    rows = analytics.label_distribution(people(member))

    assert rows[0] == {"label": "health", "count": 3}
    assert rows[1] == {"label": "admin", "count": 1}


def test_estimate_accuracy_ignores_occasions_with_no_recorded_actual(
        make_task, done_on, member):
    """`effective_minutes` falls back to the plan when no actual was recorded,
    and feeding that back in here would compare the estimate against itself and
    report perfect accuracy forever."""
    task = make_task(title="Timed", planned_minutes=30)
    done_on(1, task=task, minutes=None)

    assert analytics.estimate_accuracy(people(member))["count"] == 0


def test_estimate_accuracy_above_one_means_things_take_longer(make_task, done_on,
                                                              member):
    task = make_task(title="Timed", planned_minutes=30)
    done_on(1, task=task, minutes=60)

    result = analytics.estimate_accuracy(people(member))

    assert result["ratio"] == 2.0
    assert result["count"] == 1


def test_streak_returns_both_shapes_at_once(done_on, member):
    """The preset picks which one is shown, not this function — which is what
    lets someone switch tone and see the other number with no recomputation."""
    done_on(0)
    done_on(1)
    done_on(5)

    result = analytics.streak(people(member))

    assert result["ratio_done"] == 3
    assert result["ratio_of"] == 30
    assert result["classic"] == 2


def test_a_retroactive_edit_changes_the_number_immediately(done_on, member):
    """§13's no-stored-counters rule, tested as behaviour rather than trusted:
    history is editable, so a cached "19 of 30" would go silently wrong."""
    instance = done_on(1)
    before = analytics.streak(people(member))["ratio_done"]

    instance.outcome = InstanceOutcome.MISSED
    instance.completed_at = None
    instance.save()

    assert before == 1
    assert analytics.streak(people(member))["ratio_done"] == 0


def test_overview_is_only_a_convenience_over_the_same_functions(done_on, member):
    done_on(1)
    everything = analytics.overview(people(member))

    assert everything["streak"] == analytics.streak(people(member))
    assert everything["load"] == analytics.open_load(people(member))
    assert set(everything) >= {"throughput", "load", "streak", "flow", "heatmap"}


# ── tone ─────────────────────────────────────────────────────────────────────

def test_standard_is_the_default_before_anyone_visits_settings(member):
    """The wall and the kiosk render for people who may never open the page."""
    assert tone.resolve(member) == tone.PRESETS[Tone.STANDARD]


def test_calm_never_reddens_a_number_and_competitive_always_does(member):
    calm = tone.PRESETS[Tone.CALM]
    competitive = tone.PRESETS[Tone.COMPETITIVE]

    assert tone.may_show_red("overdue", calm) is False
    assert tone.may_show_red("overdue", competitive) is True
    assert tone.may_show_red("anything", tone.PRESETS[Tone.STANDARD]) is False


def test_wording_changes_but_the_number_does_not(member):
    """§10: nothing is withheld from anyone; only how it is said moves."""
    gentle = tone.describe_overdue(11, tone.PRESETS[Tone.CALM])
    plain = tone.describe_overdue(11, tone.PRESETS[Tone.STANDARD])

    assert "11" in gentle and "11" in plain
    assert gentle != plain


def test_an_override_sits_underneath_the_preset(member):
    TodoPreference.objects.create(member=member, tone=Tone.CALM,
                                  tone_overrides={"streaks": "classic"})

    settings = tone.resolve(member)

    assert settings["streaks"] == "classic"        # the override
    assert settings["counts_in_red"] == "never"    # still Calm underneath


def test_a_stale_override_is_ignored_rather_than_raising(member):
    """A row written by an older version must not break somebody's dashboard."""
    TodoPreference.objects.create(
        member=member, tone=Tone.STANDARD,
        tone_overrides={"gone_setting": "x", "streaks": "nonsense"})

    settings = tone.resolve(member)

    assert settings["streaks"] == "ratio"
    assert "gone_setting" not in settings


def test_every_preset_sets_every_setting(member):
    """A preset missing a key would fall through to whatever the last one set."""
    for preset in tone.PRESETS.values():
        assert set(preset) == set(tone.SETTINGS)


def test_every_setting_has_wording_for_all_of_its_values():
    """The settings page renders from WORDING; a missing row would show a bare
    `False` or `None` to a person."""
    for key, allowed in tone.SETTINGS.items():
        assert key in tone.WORDING
        for value in allowed:
            assert tone.describe(key, value) != str(value)


# ── the Reporting page ───────────────────────────────────────────────────────

def test_reporting_renders_for_someone_with_no_history(client, member):
    """The state every new house is in, and the one most likely to 500."""
    client.force_login(member)

    response = client.get(reverse("todo:reporting"))

    assert response.status_code == 200


def test_an_empty_chart_is_a_sentence_not_an_axis(client, member):
    """§10's first rule of Visual discipline, checked on the real response."""
    client.force_login(member)

    response = client.get(reverse("todo:reporting"))
    body = response.content.decode()

    assert response.context["charts"]["flow"] is None
    assert "Nothing to plot yet." in body
    assert 'data-todo-chart="chart-flow"' not in body


def test_a_chart_with_data_is_drawn(client, done_on, member):
    client.force_login(member)
    done_on(1)

    response = client.get(reverse("todo:reporting"))

    assert response.context["charts"]["flow"] is not None
    assert 'data-todo-chart="chart-flow"' in response.content.decode()


def test_reporting_sets_no_colours(client, done_on, member):
    """CLAUDE.md §4: widgets return data, the house applies the theme. A colour
    set here is a chart that stops matching the rest of the house."""
    client.force_login(member)
    done_on(1)

    charts = client.get(reverse("todo:reporting")).context["charts"]

    for option in charts.values():
        if option:
            assert "color" not in option
            assert all("color" not in s for s in option.get("series", []))


def test_reporting_says_overdue_in_the_readers_own_wording(client, make_task, member):
    TodoPreference.objects.create(member=member, tone=Tone.CALM)
    task = make_task(title="Late")
    Instance.objects.create(task=task, due_at=timezone.now() - timedelta(days=1))
    client.force_login(member)

    response = client.get(reverse("todo:reporting"))

    assert response.context["red_overdue"] is False
    assert "Moved" in response.context["overdue_phrase"]


def test_the_reporting_page_needs_a_login(client):
    response = client.get(reverse("todo:reporting"))

    assert response.status_code == 302


# ── the settings page ────────────────────────────────────────────────────────

def test_settings_renders_before_a_preference_row_exists(client, member):
    client.force_login(member)

    response = client.get(reverse("todo:settings"))

    assert response.status_code == 200
    assert TodoPreference.objects.filter(member=member).exists()


def test_settings_shows_every_preset_spelled_out(client, member):
    client.force_login(member)

    cards = client.get(reverse("todo:settings")).context["tone_cards"]

    assert [card["value"] for card in cards] == [t for t, _ in Tone.choices]
    assert all(len(card["lines"]) == len(tone.SETTINGS) for card in cards)


def test_choosing_a_preset_saves_it(client, member):
    client.force_login(member)

    client.post(reverse("todo:settings"), {"tone": Tone.COMPETITIVE})

    assert TodoPreference.objects.get(member=member).tone == Tone.COMPETITIVE


def test_an_override_posted_from_the_form_actually_takes(client, member):
    """The form posts `str(value)`; the view matches on `str(value)`. If those
    two ever disagree the override is silently dropped and the page still looks
    like it saved."""
    client.force_login(member)

    client.post(reverse("todo:settings"),
                {"tone": Tone.CALM, "override_streaks": "classic"})

    assert tone.resolve(member)["streaks"] == "classic"


def test_a_non_string_override_survives_the_round_trip(client, member):
    """`upcoming_count` is 3, 5 or None and `compare_members` is a bool — the
    values most likely to come back from a form as the string "None"."""
    client.force_login(member)

    client.post(reverse("todo:settings"), {
        "tone": Tone.CALM,
        "override_upcoming_count": "None",
        "override_compare_members": "True",
    })

    settings = tone.resolve(member)
    assert settings["upcoming_count"] is None
    assert settings["compare_members"] is True


def test_following_the_preset_stores_no_override(client, member):
    client.force_login(member)

    client.post(reverse("todo:settings"),
                {"tone": Tone.CALM, "override_streaks": "preset"})

    assert TodoPreference.objects.get(member=member).tone_overrides == {}


def test_a_junk_tone_is_ignored_rather_than_saved(client, member):
    client.force_login(member)

    client.post(reverse("todo:settings"), {"tone": "smug"})

    assert TodoPreference.objects.get(member=member).tone == Tone.STANDARD


def test_the_preset_option_shows_the_preset_not_the_pinned_value(client, member):
    """Otherwise "follow the preset" echoes back whatever is already pinned on
    top of it, and switching preset afterwards looks like it did nothing."""
    TodoPreference.objects.create(member=member, tone=Tone.CALM,
                                  tone_overrides={"streaks": "classic"})
    client.force_login(member)

    rows = {row["key"]: row
            for row in client.get(reverse("todo:settings")).context["overrides"]}

    assert rows["streaks"]["following_preset"] is False
    assert rows["streaks"]["preset_label"] == tone.describe("streaks", "ratio")


def test_the_default_due_hour_can_be_changed(client, member):
    client.force_login(member)

    client.post(reverse("todo:settings"), {"tone": Tone.STANDARD,
                                           "default_due_hour": "7"})

    assert TodoPreference.objects.get(member=member).default_due_hour == 7


def test_an_out_of_range_due_hour_is_refused(client, member):
    client.force_login(member)

    client.post(reverse("todo:settings"), {"tone": Tone.STANDARD,
                                           "default_due_hour": "99"})

    assert TodoPreference.objects.get(member=member).default_due_hour == 9
