"""
Uninstall a house app.

    python manage.py uninstall_app workout
    python manage.py uninstall_app workout --purge-data --yes
    python manage.py uninstall_app workout --remove-files --yes

By default this only unregisters the app: it comes out of `NORA_HOME_HOUSE_APPS`
in .env, so it stops appearing in the nav, on the dashboard, and on the wall —
but its code, migrations, and database tables are all left exactly as they are.
That is deliberate: `install_app houseapps.workout` re-registers it later with
every row of data still there, no different from re-enabling a paused app.

--purge-data additionally unapplies its migrations (`migrate <label> zero`),
which drops its tables. --remove-files additionally deletes houseapps/<name>/
from disk (and from this repo's git history, if it was committed there by
install_app). Both are real data loss and refuse to run without --yes.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from nora_home.core.registry import registered_apps


class Command(BaseCommand):
    help = "Uninstall a house app: unregister it, and optionally purge its data or files."

    def add_arguments(self, parser):
        parser.add_argument("name", help="App name under houseapps/, or its dotted module.")
        parser.add_argument("--purge-data", action="store_true",
                            help="Also drop the app's database tables (migrate zero).")
        parser.add_argument("--remove-files", action="store_true",
                            help="Also delete houseapps/<name>/ from disk and git.")
        parser.add_argument("--yes", action="store_true",
                            help="Required to actually perform --purge-data or --remove-files.")

    def handle(self, *args, **options):
        name = options["name"]
        self._refuse_if_level_1_or_2(name)
        module = name if name.startswith("houseapps.") else f"houseapps.{name}"
        label = module.rsplit(".", 1)[-1]
        base = Path(settings.BASE_DIR)
        target = base / "houseapps" / label

        destructive = options["purge_data"] or options["remove_files"]
        if destructive and not options["yes"]:
            raise CommandError(
                "--purge-data and --remove-files delete real data. Re-run with --yes "
                "when you mean it. Without either flag, uninstall_app only unregisters "
                "the app and leaves its code and data untouched."
            )

        if module not in settings.NORA_HOME_HOUSE_APPS:
            raise CommandError(
                f"{module} is not in NORA_HOME_HOUSE_APPS. Check `python manage.py "
                "list_apps` for the exact name."
            )

        if options["purge_data"]:
            self._purge_data(label)

        self._unregister(base, module)

        if options["remove_files"]:
            self._remove_files(base, target, module)

        # Written *before* the "done" line but after the work, and deliberately
        # at warning severity when data was purged: an app being unmounted is
        # reversible and routine, tables being dropped is neither, and the House
        # log should not make those look like the same event.
        from nora_home.core.audit import record

        record("core", "app.uninstalled", subject=module, source="cli",
               severity="warning" if destructive else "notice",
               purged_data=bool(options["purge_data"]),
               removed_files=bool(options["remove_files"]))

        self.stdout.write(self.style.SUCCESS(f"\nUninstalled {module}."))
        if not destructive:
            self.stdout.write(
                f"Code and data were left in place. `install_app {module}` brings it "
                "back exactly as it was. Restart the services to drop it from the nav: "
                "docker compose up -d"
            )
        else:
            self.stdout.write("Restart the services to apply: docker compose up -d")

    # ── steps ─────────────────────────────────────────────────────────────────
    def _refuse_if_level_1_or_2(self, name: str):
        """This command auto-prefixes anything it is given with `houseapps.`,
        which already means it can never structurally address a Level 1 or 2
        app — those live outside houseapps/ entirely. Without this check,
        trying anyway just fails later with a generic "not in
        NORA_HOME_HOUSE_APPS" error that gives no hint why. Levels are
        documented in docs/Main_App/subsystems/todo.md §1.
        """
        for meta in registered_apps(include_disabled=True):
            if name not in (meta.slug, meta.module, meta.module.rsplit(".", 1)[-1]):
                continue
            if meta.level >= 3:
                return
            what_breaks = (
                "scheduling, reminders, and escalation throughout the house"
                if meta.slug == "todo" else
                "features across the base platform that call its published API"
            )
            raise CommandError(
                f"{meta.module} is a Level {meta.level} app — the base platform "
                f"depends on it (see docs/Main_App/subsystems/todo.md §1). "
                f"Removing it would break {what_breaks}. This command only ever "
                "manages apps under houseapps/, and cannot uninstall it."
            )

    def _purge_data(self, label: str):
        """Unapply every migration for this app, dropping its tables.

        Must happen before _unregister(): this process's app registry reflects
        .env as it was when the command started, so the app is still importable
        here even though we are about to remove it from .env for good.
        """
        if label not in {cfg.label for cfg in django_apps.get_app_configs()}:
            raise CommandError(f"App label '{label}' is not currently installed.")
        self.stdout.write(f"Dropping {label}'s tables (migrate {label} zero)...")
        try:
            call_command("migrate", label, "zero", interactive=False)
        except Exception as exc:
            raise CommandError(f"migrate {label} zero failed: {exc}")

    def _unregister(self, base: Path, module: str):
        env_path = base / ".env"
        if not env_path.exists():
            raise CommandError(".env does not exist.")

        lines = env_path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not line.startswith("NORA_HOME_HOUSE_APPS="):
                continue
            current = [m.strip() for m in line.split("=", 1)[1].split(",") if m.strip()]
            if module not in current:
                return
            current.remove(module)
            lines[index] = "NORA_HOME_HOUSE_APPS=" + ",".join(current)
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.stdout.write(f"  removed {module} from .env ({len(current)} house apps left)")
            return
        raise CommandError(f"NORA_HOME_HOUSE_APPS line not found in .env for {module}.")

    def _remove_files(self, base: Path, target: Path, module: str):
        if not target.exists():
            self.stderr.write(f"  {target} does not exist; nothing to remove on disk.")
            return

        relpath = module.replace(".", "/")
        tracked = False
        if shutil.which("git") is not None:
            result = subprocess.run(["git", "ls-files", "--error-unmatch", relpath],
                                    cwd=base, capture_output=True, timeout=30)
            tracked = result.returncode == 0

        if tracked:
            subprocess.run(["git", "rm", "-rq", relpath], cwd=base, check=True,
                            capture_output=True, timeout=60)
            subprocess.run(["git", "commit", "-m", f"Uninstall house app: {module}"],
                            cwd=base, capture_output=True, timeout=60)
            self.stdout.write(f"  removed {relpath} and committed the removal")
        else:
            shutil.rmtree(target)
            self.stdout.write(f"  deleted {relpath} (was not tracked in git)")
