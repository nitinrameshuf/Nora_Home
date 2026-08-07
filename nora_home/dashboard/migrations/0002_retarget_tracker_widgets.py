"""
Point every stored layout at Todo's widgets, now that the tracker's are gone.

`DashboardLayout` skips a key it cannot resolve rather than deleting it, so
nothing broke when Story 40 deleted `nora_home.tracker` — but "nothing broke"
meant every home screen in the house, *including the always-on wall*, silently
lost three or four of its tiles and kept only `core.HouseHealthWidget`. Graceful
degradation is the right behaviour for an app someone uninstalled; it is the
wrong outcome for widgets that have exact successors sitting right there.

The mapping keeps each tile's *kind*, because a layout is a grid of boxes with
stored widths and heights: a list widget replaced by a stat would be a stat
stretched across a box drawn for a list.

    tracker.TodayWidget        list  -> todo.DueNextWidget            list
    tracker.OverdueWidget      list  -> todo.OpenLoadWidget           stat
    tracker.ReliabilityWidget  chart -> todo.CompletionHeatmapWidget  chart
    tracker.StreakWidget       stat  -> todo.StreakWidget             stat

`OverdueWidget` is the one exception, and deliberately: Todo has no overdue
*list*, and "Open now" is the closest thing that answers the same question
("what is late?"). It will sit in a box drawn for a list until someone resizes
it, which is a cosmetic cost worth paying to keep the tile rather than lose it.
"""

from django.db import migrations

REPLACEMENTS = {
    "tracker.TodayWidget": "todo.DueNextWidget",
    "tracker.OverdueWidget": "todo.OpenLoadWidget",
    "tracker.ReliabilityWidget": "todo.CompletionHeatmapWidget",
    "tracker.StreakWidget": "todo.StreakWidget",
}


def retarget(apps, schema_editor):
    DashboardLayout = apps.get_model("dashboard", "DashboardLayout")

    for layout in DashboardLayout.objects.all():
        items, seen, changed = [], set(), False
        for item in layout.items or []:
            key = item.get("key")
            replacement = REPLACEMENTS.get(key)
            if replacement:
                item = {**item, "key": replacement}
                changed = True
            # A layout that already held the replacement would otherwise end up
            # with the same widget twice — two tiles rendering identical content,
            # which reads as a bug rather than as a choice.
            if item.get("key") in seen:
                changed = True
                continue
            seen.add(item.get("key"))
            items.append(item)

        if changed:
            layout.items = items
            layout.save(update_fields=["items"])


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0001_initial"),
    ]

    operations = [
        # No reverse: the tracker's widgets no longer exist to point back at.
        migrations.RunPython(retarget, migrations.RunPython.noop),
    ]
