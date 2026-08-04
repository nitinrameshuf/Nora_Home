"""
Install a house app in one command.

    python manage.py install_app https://github.com/nitin/nora-workout
    python manage.py install_app ../nora-workout
    python manage.py install_app houseapps.workout        # already on disk

It clones (or copies) the app into houseapps/, verifies it declares a
NoraAppConfig, registers it in .env, generates and applies its migrations,
collects its static files, and commits the app into this platform repo's own git
history. That last step is what makes the app survive a fresh clone or a
dropped SD card — houseapps/ is otherwise just loose files on one Pi's disk.

Deliberately conservative: it refuses rather than guesses when something looks
wrong, because a half-installed app that breaks the wall display is worse than a
failed install.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

MODULE_RE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*$")


class Command(BaseCommand):
    help = "Install a house app from a git URL, a local path, or an existing module."

    def add_arguments(self, parser):
        parser.add_argument("source", help="Git URL, local directory, or dotted module.")
        parser.add_argument("--name", help="Directory name under houseapps/.")
        parser.add_argument("--branch", default="", help="Git branch to check out.")
        parser.add_argument("--no-migrate", action="store_true",
                            help="Skip generating and applying migrations.")

    def handle(self, *args, **options):
        source = options["source"]
        base = Path(settings.BASE_DIR)
        houseapps = base / "houseapps"
        houseapps.mkdir(exist_ok=True)

        if source.startswith(("http://", "https://", "git@")):
            module = self._from_git(source, houseapps, options)
        elif MODULE_RE.match(source) and (base / source.replace(".", "/")).exists():
            module = source
        else:
            module = self._from_path(Path(source).expanduser(), houseapps, options)

        self._verify(base, module)
        self._register(base, module)

        if not options["no_migrate"]:
            self._migrate(module)

        self._commit(base, module)

        self.stdout.write(self.style.SUCCESS(f"\nInstalled {module}."))
        self.stdout.write("Restart the services to mount it: docker compose up -d")

    # ── acquisition ────────────────────────────────────────────────────────────
    def _from_git(self, url: str, houseapps: Path, options) -> str:
        name = options["name"] or Path(url.rstrip("/")).name
        name = re.sub(r"^nora[-_]", "", name).replace("-", "_").removesuffix(".git")
        target = houseapps / name

        if target.exists():
            raise CommandError(
                f"{target} already exists. Remove it first, or pass --name to install "
                "alongside the existing copy."
            )
        if shutil.which("git") is None:
            raise CommandError("git is not installed in this environment.")

        command = ["git", "clone", "--depth", "1"]
        if options["branch"]:
            command += ["--branch", options["branch"]]
        command += [url, str(target)]

        self.stdout.write(f"Cloning {url} -> houseapps/{name}")
        try:
            subprocess.run(command, check=True, timeout=300, capture_output=True)
        except subprocess.CalledProcessError as exc:
            raise CommandError(f"git clone failed: {exc.stderr.decode()[:400]}")

        # The app's own git history is not this repo's business.
        shutil.rmtree(target / ".git", ignore_errors=True)
        return f"houseapps.{name}"

    def _from_path(self, path: Path, houseapps: Path, options) -> str:
        if not path.is_dir():
            raise CommandError(f"{path} is not a directory, a git URL, or a module.")

        name = options["name"] or path.name.replace("-", "_")
        target = houseapps / name
        if target.exists():
            raise CommandError(f"houseapps/{name} already exists.")

        self.stdout.write(f"Copying {path} -> houseapps/{name}")
        shutil.copytree(path, target,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        return f"houseapps.{name}"

    # ── checks ────────────────────────────────────────────────────────────────
    def _verify(self, base: Path, module: str):
        directory = base / module.replace(".", "/")

        if not (directory / "__init__.py").exists():
            raise CommandError(f"{module} has no __init__.py; it is not a Python package.")

        apps_py = directory / "apps.py"
        if not apps_py.exists():
            raise CommandError(
                f"{module} has no apps.py. Every house app must declare a "
                "NoraAppConfig — see docs/Main_App/DEVELOPMENT.md."
            )
        if "NoraAppConfig" not in apps_py.read_text(encoding="utf-8"):
            raise CommandError(
                f"{module}/apps.py does not subclass NoraAppConfig, so the platform "
                "cannot place it. See docs/Main_App/DEVELOPMENT.md."
            )
        self.stdout.write("  apps.py declares a NoraAppConfig [ok]")

        # Every house app is required to document itself, in its own folder
        # under docs/House_Apps/. Warned rather than fatal: a missing doc is a
        # documentation problem, and refusing to install working code over it
        # would just teach people to commit an empty file.
        name = module.rsplit(".", 1)[-1]
        app_docs = base / "docs" / "House_Apps" / name
        if (app_docs / "README.md").exists():
            self.stdout.write(f"  docs/House_Apps/{name}/README.md present [ok]")
        else:
            self.stdout.write(self.style.WARNING(
                f"  {module} has no docs. Every house app needs "
                f"docs/House_Apps/{name}/README.md — what it is for, where it "
                "appears on each screen, what it owns, and what it exposes to "
                "other apps. See docs/House_Apps/README.md for the required "
                "sections, and copy docs/House_Apps/example_habit/README.md."
            ))
            if app_docs.exists():
                self.stdout.write(f"    (docs/House_Apps/{name}/ exists but has no README.md)")

    def _register(self, base: Path, module: str):
        """Add the module to NORA_HOME_HOUSE_APPS in .env, creating the line if needed."""
        env_path = base / ".env"
        if not env_path.exists():
            raise CommandError(".env does not exist. Run `make up` once first.")

        lines = env_path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not line.startswith("NORA_HOME_HOUSE_APPS="):
                continue
            current = [m.strip() for m in line.split("=", 1)[1].split(",") if m.strip()]
            if module in current:
                self.stdout.write(f"  {module} was already registered")
                return
            current.append(module)
            lines[index] = "NORA_HOME_HOUSE_APPS=" + ",".join(current)
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.stdout.write(f"  registered in .env ({len(current)} house apps)")
            return

        existing = list(settings.NORA_HOME_HOUSE_APPS)
        if module not in existing:
            existing.append(module)
        lines.append("NORA_HOME_HOUSE_APPS=" + ",".join(existing))
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.stdout.write(f"  added NORA_HOME_HOUSE_APPS to .env ({len(existing)} apps)")

    def _migrate(self, module: str):
        """Run makemigrations/migrate/collectstatic as fresh subprocesses.

        This process's Django app registry was already populated — from the .env
        that existed *before* `_register()` just rewrote it — when this command
        started. Calling `call_command()` in-process would look for the new app in
        that stale registry and fail with "No installed app with label ...", even
        though the app is now correctly listed in .env. A fresh `manage.py`
        subprocess re-reads .env from scratch and sees the app immediately.
        """
        label = module.rsplit(".", 1)[-1]
        manage_py = Path(settings.BASE_DIR) / "manage.py"

        self.stdout.write("Generating migrations...")
        result = subprocess.run([sys.executable, str(manage_py), "makemigrations", label],
                                cwd=settings.BASE_DIR, capture_output=True, text=True)
        # An app with no models exits non-zero too; only warn, since that is normal.
        for line in (result.stdout + result.stderr).splitlines():
            if line.strip():
                self.stdout.write(f"  {line}")

        self.stdout.write("Applying migrations...")
        result = subprocess.run([sys.executable, str(manage_py), "migrate"],
                                cwd=settings.BASE_DIR, capture_output=True, text=True)
        if result.returncode != 0:
            raise CommandError(f"migrate failed:\n{result.stderr[-2000:]}")
        for line in result.stdout.splitlines():
            if line.strip():
                self.stdout.write(f"  {line}")

        self.stdout.write("Collecting static files...")
        result = subprocess.run(
            [sys.executable, str(manage_py), "collectstatic", "--noinput", "-v", "0"],
            cwd=settings.BASE_DIR, capture_output=True, text=True)
        if result.returncode != 0:
            self.stdout.write(f"  collectstatic: {result.stderr[-500:]}")

    # ── durability ────────────────────────────────────────────────────────────
    def _commit(self, base: Path, module: str):
        """Commit the app into this platform repo so it survives a fresh clone.

        Without this, houseapps/<name> is just loose files on one Pi's disk: a
        re-clone, a dead SD card, or `rm -rf` leaves its data orphaned in the
        database with no code left to read it. Non-fatal on failure — a family
        member may not have git configured for commits — but loud, since it is
        the only thing standing between "installed" and "gone at the next reset."
        """
        if shutil.which("git") is None:
            self.stderr.write("git not available; app was NOT committed. It exists "
                               "only on this machine's disk until you commit it yourself.")
            return

        relpath = module.replace(".", "/")
        try:
            subprocess.run(["git", "add", relpath], cwd=base, check=True,
                            capture_output=True, timeout=60)
            result = subprocess.run(
                ["git", "commit", "-m", f"Install house app: {module}"],
                cwd=base, capture_output=True, text=True, timeout=60,
            )
        except subprocess.CalledProcessError as exc:
            self.stderr.write(f"git add failed; app was NOT committed: {exc.stderr}")
            return

        if result.returncode != 0:
            # "nothing to commit" (e.g. re-registering an app already on disk) is fine.
            if "nothing to commit" in (result.stdout + result.stderr):
                return
            self.stderr.write(
                f"git commit failed; app was NOT committed: {result.stderr[-400:]}\n"
                "It will be lost on a fresh clone until you commit it by hand."
            )
            return
        self.stdout.write(f"  committed {relpath} to the platform repo")
