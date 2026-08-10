"""
Story 48: layouts stop storing coordinates and start storing a size.

Every stored item was {"key", "x", "y", "w", "h"} on a 12-column grid with an
~80px row. They become {"key", "size"} where size is one of S/M/L/XL, and the
list's *order* is the layout — CSS grid places them.

Order is recovered from the old coordinates (top to bottom, then left to right),
which is the only place it existed. Doing that first matters: a naive pass in
stored order would scramble anyone's screen, because Gridstack wrote items in
whatever order they were last dragged, not in reading order.

Reversible on purpose. The old form is reconstructed by shelf-packing the sizes
back onto a 12-column grid, so a downgrade lands on a tidy arrangement rather
than a pile at 0,0 — not the identical pixels someone had before (that
information is genuinely gone once coordinates are dropped), but a working
screen, which is what reversibility is for here.
"""

from django.db import migrations

# (columns, rows) per size — kept literal rather than imported from
# nora_home.dashboard.widgets, because a migration has to keep meaning what it
# meant when it ran, and that table is free to change.
CELLS = {"S": (3, 1), "M": (6, 1), "L": (6, 2), "XL": (12, 1)}


def _size_for(width, height):
    """Nearest size to an old (w, h). Width dominates: it is what a person
    actually sees as "how wide is that tile", and the old row height was
    ~80px against this grid's 128px, so heights do not compare directly."""
    try:
        width = int(width)
        height = int(height)
    except (TypeError, ValueError):
        return "M"

    if width >= 9:
        return "XL"
    if width <= 3:
        # A tall narrow tile has no equivalent — S is 3x1 and there is no 3x2.
        # M keeps its content readable rather than crushing a two-row widget
        # into one row a third of the width.
        return "S" if height <= 2 else "M"
    return "L" if height >= 3 else "M"


def to_sizes(apps, schema_editor):
    Layout = apps.get_model("dashboard", "DashboardLayout")
    for layout in Layout.objects.all():
        items = layout.items or []
        if not isinstance(items, list):
            layout.items = []
            layout.save(update_fields=["items"])
            continue

        ordered = []
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not item.get("key"):
                continue
            if "size" in item and "x" not in item:
                ordered.append((0, 0, index, item["key"], item["size"]))
                continue
            try:
                y = int(item.get("y", 0))
                x = int(item.get("x", 0))
            except (TypeError, ValueError):
                y = x = 0
            ordered.append((y, x, index, item["key"],
                            _size_for(item.get("w"), item.get("h"))))

        # Reading order: down the screen, then across. `index` breaks ties so
        # two tiles sharing a cell keep their stored order rather than sorting
        # by key and shuffling.
        ordered.sort(key=lambda row: (row[0], row[1], row[2]))
        layout.items = [{"key": key, "size": size} for _, _, _, key, size in ordered]
        layout.save(update_fields=["items"])


def to_coordinates(apps, schema_editor):
    Layout = apps.get_model("dashboard", "DashboardLayout")
    for layout in Layout.objects.all():
        items = layout.items or []
        if not isinstance(items, list):
            continue

        rebuilt = []
        x = y = row_height = 0
        for item in items:
            if not isinstance(item, dict) or not item.get("key"):
                continue
            width, height = CELLS.get(item.get("size"), CELLS["M"])
            if x + width > 12:          # shelf-pack: start a new row
                x, y, row_height = 0, y + (row_height or 1), 0
            rebuilt.append({"key": item["key"], "x": x, "y": y,
                            "w": width, "h": height})
            x += width
            row_height = max(row_height, height)

        layout.items = rebuilt
        layout.save(update_fields=["items"])


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0002_retarget_tracker_widgets")]

    operations = [migrations.RunPython(to_sizes, to_coordinates)]
