"""Repack every stored dashboard onto its widgets' own declared sizes.

The home screen looked disorganised in a way no stylesheet could fix, because
the raggedness was *data*. One member's layout held tiles at h=2, 3, 4 and 5
with gaps at x=3, 5, 7 and 9 — so cards genuinely were different heights and
genuinely did not line up. Meanwhile every widget class already declares a
`default_size` it wants, and nothing had ever reconciled the two.

This walks each layout, replaces w/h with the widget's declared size, and packs
left to right, top to bottom with no holes. Tiles keep their order, so a
dashboard someone arranged deliberately still reads in the same sequence.

Not run automatically: `items` is a person's own arrangement, and silently
rewriting it on deploy would be worse than the mess it cleans up. A key that no
longer resolves is left in place untouched, exactly as the render path does —
reinstalling the app should restore the tile.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from nora_home.dashboard.models import DashboardLayout
from nora_home.dashboard.widgets import all_widgets

GRID_COLUMNS = 12


def _sizes_by_key() -> dict[str, tuple[int, int]]:
    """key -> declared default_size, for every widget the house can show.

    Keys stored in a layout are `<app_slug>.<ClassName>` (Widget.key), which is
    NOT a dotted import path — passing one to load_widget() resolves nothing and
    silently leaves every layout untouched. Built from `all_widgets("admin")` so
    the map covers widgets restricted to admins too; this command re-packs
    geometry and never decides who may see what.
    """
    return {w.key: tuple(w.default_size) for w in all_widgets("admin")}


class Command(BaseCommand):
    help = "Repack dashboard layouts onto each widget's declared default size."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Show what would change, write nothing.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        touched = 0
        sizes = _sizes_by_key()

        for layout in DashboardLayout.objects.all():
            packed, x, y, row_height = [], 0, 0, 0

            for item in layout.items:
                key = item.get("key", "")
                size = sizes.get(key)
                if size is None:
                    # Unresolvable key: keep it verbatim so reinstalling the
                    # app restores the tile where it was.
                    packed.append(dict(item))
                    continue

                w, h = size
                w = max(1, min(int(w), GRID_COLUMNS))

                # Wrap to the next band once this one is full. Bands are as tall
                # as their tallest tile, which is what stops the next row
                # starting halfway up the previous one.
                if x + w > GRID_COLUMNS:
                    y += row_height
                    x, row_height = 0, 0

                packed.append({"key": key, "x": x, "y": y, "w": w, "h": int(h)})
                x += w
                row_height = max(row_height, int(h))

            if packed == layout.items:
                continue

            touched += 1
            who = layout.member or "everyone"
            self.stdout.write(f"  {layout.surface}/{who}: {len(packed)} tiles repacked")
            if not dry:
                layout.items = packed
                layout.save(update_fields=["items"])

        verb = "would change" if dry else "changed"
        self.stdout.write(self.style.SUCCESS(f"{touched} layout(s) {verb}."))
