"""Regenerate the parts of the documentation that are derived from code.

`docs/Main_App/cross-functionality.md` currently says of itself: *"Signatures
below are copied from the code, not from memory. When you change a published
function, change its row here in the same commit."* That is a hand-maintained
copy of something the code already knows, and copies rot — `register_trackable()`
survived in five documents for weeks after the app publishing it was deleted.

So the derivable parts are generated instead, between markers:

    <!-- sync_docs:begin NAME -->
    ...generated, do not edit...
    <!-- sync_docs:end NAME -->

Everything outside the markers is hand-written and never touched. Run
`manage.py sync_docs` to rewrite them; `manage.py sync_docs --check` rewrites
nothing and exits non-zero if the committed file differs from a regeneration.
`tests/test_docs_in_sync.py` runs the check, so a stale table is a red suite
rather than something noticed months later.
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from nora_home.core.registry import registered_apps

BEGIN = "<!-- sync_docs:begin {name} -->"
END = "<!-- sync_docs:end {name} -->"

# The published API modules. A module listed here has every public function in
# it documented automatically; adding a function is enough to document it.
API_MODULES = [
    "nora_home.todo.api",
    "nora_home.notifications.api",
    "nora_home.telemetry.api",
    "nora_home.core.api",
]


def _first_line(doc: str | None) -> str:
    if not doc:
        return "—"
    line = inspect.cleandoc(doc).split("\n\n")[0].replace("\n", " ").strip()
    return line.rstrip(".") or "—"


def published_api() -> str:
    """A row per public function in each app's api module, with its real
    signature. Generated, so a renamed argument cannot quietly disagree."""
    out: list[str] = []
    for dotted in API_MODULES:
        try:
            module = importlib.import_module(dotted)
        except ModuleNotFoundError:
            out.append(f"\n### `{dotted}`\n\n_Not installed._\n")
            continue

        rows = []
        for name, obj in sorted(vars(module).items()):
            if name.startswith("_") or not inspect.isfunction(obj):
                continue
            if obj.__module__ != module.__name__:
                continue  # imported into the module, published by someone else
            rows.append(f"| `{name}{inspect.signature(obj)}` | {_first_line(obj.__doc__)} |")

        out.append(f"\n### `{dotted}`\n")
        if rows:
            out.append("\n| Call | What it does |\n|---|---|")
            out.extend(rows)
            out.append("")
        else:
            out.append("\n_Publishes nothing._\n")
    return "\n".join(out).strip() + "\n"


def installed_apps_table() -> str:
    """What is registered right now, and what each app contributes. This is the
    table an author checks their own app against after installing it."""
    rows = [
        "| App | Level | URL | Nav | Sections | Widgets | Kiosk keys | MCP |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for meta in registered_apps(include_disabled=True):
        rows.append(
            f"| **{meta.title}** <br><code>{meta.module}</code> | {meta.level} | "
            f"`{meta.url}` | {'yes' if meta.nav else '—'} | "
            f"{len(meta.sections) or '—'} | {len(meta.widgets) or '—'} | "
            f"{len(meta.kiosk_controls) or '—'} | "
            f"{'yes' if meta.provides_mcp_tools else '—'} |"
        )
    return "\n".join(rows) + "\n"


def app_contract_table() -> str:
    """Every field a NoraAppConfig may declare, read off the class itself, so a
    new capability documents itself the moment it is added."""
    from nora_home.core.registry import NoraAppConfig

    rows = ["| Declare | Default | Effect |", "|---|---|---|"]
    hints = getattr(NoraAppConfig, "__annotations__", {})
    for name in sorted(n for n in dir(NoraAppConfig) if n.startswith("nora_")):
        # Data fields only. Properties and methods are not things an author
        # declares, and repr() of a property embeds its memory address — which
        # made this block differ on every run and the --check permanently red.
        attr = inspect.getattr_static(NoraAppConfig, name, None)
        if isinstance(attr, property) or callable(attr):
            continue
        default = getattr(NoraAppConfig, name)
        shown = "—" if default in ([], {}, "") else f"`{default!r}`"
        kind = hints.get(name, "")
        kind = getattr(kind, "__name__", str(kind)) if kind else ""
        rows.append(f"| `{name}`{f' · _{kind}_' if kind else ''} | {shown} | |")
    return "\n".join(rows) + "\n"


BLOCKS = {
    "published-api": (Path("docs/Main_App/cross-functionality.md"), published_api),
    "installed-apps": (Path("docs/Main_App/cross-functionality.md"), installed_apps_table),
    "app-contract": (Path("docs/Main_App/DEVELOPMENT.md"), app_contract_table),
}


class Command(BaseCommand):
    help = "Regenerate the generated blocks in docs/. --check verifies instead."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check", action="store_true",
            help="Do not write. Exit 1 if any generated block is out of date.",
        )

    def handle(self, *args, **options):
        check = options["check"]
        base = Path(settings.BASE_DIR)
        stale: list[str] = []
        missing: list[str] = []
        written: list[str] = []

        for name, (relative, build) in BLOCKS.items():
            path = base / relative
            if not path.exists():
                missing.append(f"{relative} (for block {name})")
                continue

            text = path.read_text(encoding="utf-8")
            begin, end = BEGIN.format(name=name), END.format(name=name)
            if begin not in text or end not in text:
                missing.append(f"{relative} has no '{name}' markers")
                continue

            body = build()
            pattern = re.compile(
                re.escape(begin) + r".*?" + re.escape(end), re.S)
            replacement = f"{begin}\n\n{body}\n{end}"
            updated = pattern.sub(lambda _m: replacement, text)

            if updated == text:
                continue
            if check:
                stale.append(f"{relative} :: {name}")
            else:
                path.write_text(updated, encoding="utf-8")
                written.append(f"{relative} :: {name}")

        if missing:
            for item in missing:
                self.stderr.write(f"  missing: {item}")
            raise SystemExit(2)

        if check:
            if stale:
                self.stderr.write("Generated documentation is out of date:")
                for item in stale:
                    self.stderr.write(f"  {item}")
                self.stderr.write("\nRun: manage.py sync_docs")
                raise SystemExit(1)
            self.stdout.write("docs in sync")
            return

        if written:
            for item in written:
                self.stdout.write(f"  updated: {item}")
        else:
            self.stdout.write("nothing to update")
