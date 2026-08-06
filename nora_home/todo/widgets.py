"""
Todo's widgets — what it offers the home screen and the wall.

§6 is firm that widgets are **not how Todo presents itself**; the app presents
itself as the app, and these are for the personal grid and whatever the wall
shows when pointed at `/home/`. So this is a small, chosen set rather than one
widget per chart on the Reporting page.

Every number comes from `nora_home.todo.analytics`. Nothing here computes a
statistic — that is §13's rule, and it is what lets the Reporting page, these
widgets and a future MCP tool all agree.

Two rules from §10's Visual discipline apply directly to widgets, and the
platform's own home dashboard breaks both:

* **Empty is a sentence, never an axis.** `_no_data()` returns a chart option
  with the axes switched off and one line of text. The tracker's own
  "Reliability" widget renders a full 0/0.2/…/1 axis with nothing plotted,
  which is the thing not to copy.
* **Good news is small.** The quiet state is a compact stat tile, not a
  full-size card announcing that nothing is wrong.
"""

from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from nora_home.core.registry import scope_members
from nora_home.dashboard.widgets import ChartWidget, ListWidget, StatWidget
from nora_home.todo import analytics, tone
from nora_home.todo.models import InstanceOutcome, TaskState
from nora_home.todo.scheduling import current_instance


def _no_data(message: str) -> dict:
    """A chart that has nothing to draw yet: one sentence, no axes, no grid.

    Deliberately not an empty series on a real pair of axes — a 0-to-1 axis
    with nothing plotted looks like a measurement of failure rather than an
    absence of data, and that is precisely the mistake §10 catalogues.
    """
    return {
        "title": {"text": message, "left": "center", "top": "middle",
                  "textStyle": {"fontSize": 13, "fontWeight": "normal"}},
        "xAxis": {"show": False},
        "yAxis": {"show": False},
        "series": [],
    }


class OpenLoadWidget(StatWidget):
    title = "Open now"
    description = "How much is actually open, and how much of it is late."
    icon = "target"
    default_size = (3, 2)
    refresh_seconds = 300

    def stat(self, request):
        members = scope_members(request)
        load = analytics.open_load(members)
        settings = tone.resolve(request.user)

        overdue = load["overdue"]
        # Tone decides the colour, never the number — §10: "Nothing is withheld
        # from anyone." Someone on Calm still sees that 3 are overdue; it just
        # is not shouted at them in red.
        status = "alert" if overdue and tone.may_show_red("overdue", settings) else "ok"

        if overdue:
            delta = tone.describe_overdue(overdue, settings)
        else:
            delta = "nothing late"

        return {"value": load["count"], "label": "open", "delta": delta,
                "status": status}


class TypicalThroughputWidget(StatWidget):
    title = "You typically finish"
    subtitle = "Per day, over 90 days"
    description = ("What a realistic day actually looks like for you — the "
                   "median, not an average nobody ever hits.")
    icon = "chart"
    default_size = (3, 2)
    refresh_seconds = 3600

    def stat(self, request):
        data = analytics.typical_throughput(scope_members(request))
        if data["median"] is None:
            # Not zero. Nothing has been finished yet, which is a different
            # statement and must not read as a score of 0.
            return {"value": "—", "label": "not enough history yet", "status": "ok"}

        low, high = data["low"], data["high"]
        band = f"{low}–{high} on a normal day" if low != high else "steady"
        return {"value": data["median"], "label": "things a day",
                "delta": band, "status": "ok"}


class StreakWidget(StatWidget):
    title = "Keeping at it"
    description = ("Days with something finished. Shows a rolling ratio, or a "
                   "classic resets-on-a-miss streak, depending on your tone.")
    icon = "spark"
    default_size = (3, 2)
    refresh_seconds = 900

    def stat(self, request):
        data = analytics.streak(scope_members(request))
        settings = tone.resolve(request.user)

        if settings["streaks"] == "classic":
            return {"value": data["classic"], "label": "day streak",
                    "status": "ok"}
        return {"value": f"{data['ratio_done']} of {data['ratio_of']}",
                "label": "days with something done", "status": "ok"}


class DueNextWidget(ListWidget):
    title = "Due next"
    description = "The next few things of yours, soonest first."
    icon = "sun"
    default_size = (4, 4)
    refresh_seconds = 120
    empty_message = "Nothing due. Enjoy it."

    def rows(self, request):
        members = scope_members(request)
        settings = tone.resolve(request.user)
        # §10's Tone table: Calm shows the next 3, Standard 5, Competitive all.
        limit = settings["upcoming_count"] or 50

        instances = (analytics.instances_of(members)
                     .filter(outcome=InstanceOutcome.PENDING,
                             task__state=TaskState.OPEN)
                     .order_by("due_at")[:limit])
        now = timezone.now()

        return [{
            "title": instance.task.title,
            "meta": timezone.localtime(instance.due_at).strftime("%a %H:%M"),
            "status": "alert" if instance.due_at < now and tone.may_show_red(
                "overdue", settings) else "ok",
            "url": reverse("todo:detail", args=[instance.task.uuid]),
            "action_url": reverse("todo:complete", args=[instance.uuid]),
        } for instance in instances]


class CompletionHeatmapWidget(ChartWidget):
    title = "The year so far"
    subtitle = "Days with something finished"
    description = "A calendar heatmap of everything completed over the last year."
    icon = "calendar"
    default_size = (12, 3)
    refresh_seconds = 3600
    wall_safe = True

    def option(self, request):
        data = analytics.completion_heatmap(scope_members(request))
        if not data:
            return _no_data("Nothing finished yet.")

        today = timezone.localdate()
        return {
            "tooltip": {"trigger": "item"},
            "visualMap": {"min": 0, "max": max(count for _, count in data) or 1,
                          "type": "piecewise", "orient": "horizontal",
                          "left": "center", "top": 0, "showLabel": False},
            "calendar": {
                # 365 days rather than `replace(year=year - 1)`, which raises
                # on 29 February and would take the home screen down with it.
                "range": [str(today - timedelta(days=365)), str(today)],
                "cellSize": ["auto", 13], "top": 50,
                "splitLine": {"show": False},
                "itemStyle": {"borderWidth": 2},
                "yearLabel": {"show": False},
            },
            "series": [{"type": "heatmap", "coordinateSystem": "calendar",
                        "data": data}],
        }


class CumulativeFlowWidget(ChartWidget):
    title = "Arriving vs finishing"
    subtitle = "Last 60 days"
    description = ("Whether the pile is growing. Two lines pulling apart means "
                   "more is arriving than leaving.")
    icon = "chart"
    default_size = (6, 4)
    refresh_seconds = 1800

    def option(self, request):
        flow = analytics.cumulative_flow(scope_members(request))
        if not flow["days"]:
            return _no_data("Nothing to plot yet.")

        return {
            "xAxis": {"type": "category", "data": flow["days"],
                      "axisLabel": {"showMaxLabel": True}},
            "yAxis": {"type": "value", "name": "items"},
            "legend": {"data": ["Arrived", "Finished"]},
            "series": [
                {"name": "Arrived", "type": "line", "areaStyle": {},
                 "showSymbol": False, "data": flow["arrived"]},
                {"name": "Finished", "type": "line", "areaStyle": {},
                 "showSymbol": False, "data": flow["completed"]},
            ],
        }
