"""
Restore a backup produced by `nora_backup`.

    python manage.py nora_restore /var/backups/nora/nora-20260730-030000
    python manage.py nora_restore backup.tar.gz --from-fixtures   # engine migration

Two modes:

  SQL restore (default)     exact, fast, requires the same database engine.
  --from-fixtures           loads fixtures/all.json through the ORM, so it works
                            across engines — sqlite → MySQL, or onto a new machine.

This overwrites live data. The command refuses to run without --yes, and prints the
manifest first so you can see what you are about to restore.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Restore a Nora Home backup. Overwrites current data."

    def add_arguments(self, parser):
        parser.add_argument("source", help="Backup directory or .tar.gz.")
        parser.add_argument("--from-fixtures", action="store_true",
                            help="Restore via the portable ORM dump (cross-engine).")
        parser.add_argument("--skip-mongo", action="store_true")
        parser.add_argument("--skip-media", action="store_true")
        parser.add_argument("--yes", action="store_true",
                            help="Confirm that live data may be overwritten.")

    def handle(self, *args, **options):
        source = Path(options["source"])
        if not source.exists():
            raise CommandError(f"No such backup: {source}")

        with tempfile.TemporaryDirectory() as scratch:
            root = self._unpack(source, Path(scratch))
            manifest = self._read_manifest(root)

            self.stdout.write(self.style.WARNING("About to restore:"))
            self.stdout.write(json.dumps(manifest, indent=2))

            if not options["yes"]:
                raise CommandError(
                    "Refusing to overwrite live data. Re-run with --yes when you are "
                    "sure this is the backup you want."
                )

            # Schema first — a fixture load needs tables to load into.
            call_command("migrate", interactive=False, verbosity=1)

            if options["from_fixtures"]:
                self._load_fixtures(root)
            else:
                self._restore_sql(root, manifest)

            if not options["skip_mongo"]:
                self._restore_mongo(root)
            if not options["skip_media"]:
                self._restore_media(root)

        self.stdout.write(self.style.SUCCESS(
            "Restore complete. Restart the web and worker services."))

    # ── steps ──────────────────────────────────────────────────────────────────
    def _unpack(self, source: Path, scratch: Path) -> Path:
        if source.is_dir():
            return source
        self.stdout.write(f"Extracting {source.name}...")
        with tarfile.open(source, "r:gz") as tar:
            tar.extractall(scratch, filter="data")
        entries = [p for p in scratch.iterdir() if p.is_dir()]
        if not entries:
            raise CommandError("The archive did not contain a backup directory.")
        return entries[0]

    def _read_manifest(self, root: Path) -> dict:
        manifest = root / "manifest.json"
        if not manifest.exists():
            raise CommandError("manifest.json is missing; this is not a Nora backup.")
        return json.loads(manifest.read_text())

    def _load_fixtures(self, root: Path):
        fixture = root / "fixtures" / "all.json"
        if not fixture.exists():
            raise CommandError("This backup has no fixtures/all.json to restore from.")
        self.stdout.write("Loading fixtures through the ORM (cross-engine restore)…")
        call_command("loaddata", str(fixture))

    def _restore_sql(self, root: Path, manifest: dict):
        db = settings.DATABASES["default"]
        part = manifest.get("parts", {}).get("sql", {})

        if part.get("kind") == "sqlite":
            if "sqlite" not in db["ENGINE"]:
                raise CommandError(
                    "This backup holds a SQLite database but the current settings use "
                    "MySQL. Re-run with --from-fixtures to migrate across engines."
                )
            shutil.copy2(root / "sql" / "db.sqlite3", db["NAME"])
            self.stdout.write("Restored the SQLite database file.")
            return

        dump = root / "sql" / "nora_home.sql"
        if not dump.exists():
            raise CommandError("No SQL dump found. Try --from-fixtures.")
        if "mysql" not in db["ENGINE"]:
            raise CommandError(
                "This backup holds a MySQL dump but the current settings do not use "
                "MySQL. Re-run with --from-fixtures."
            )
        if shutil.which("mysql") is None:
            raise CommandError("The `mysql` client is not installed.")

        import os

        self.stdout.write("Restoring the MySQL dump...")
        with dump.open("rb") as handle:
            subprocess.run(
                ["mysql", f"--host={db['HOST']}", f"--port={db['PORT']}",
                 f"--user={db['USER']}", db["NAME"]],
                stdin=handle, check=True,
                env={**os.environ, **({"MYSQL_PWD": db["PASSWORD"]}
                                      if db["PASSWORD"] else {})},
            )

    def _restore_mongo(self, root: Path):
        archive = root / "mongo" / "nora_home.archive.gz"
        if not archive.exists():
            return
        if shutil.which("mongorestore") is None:
            self.stderr.write("mongorestore not installed; skipping documents.")
            return
        self.stdout.write("Restoring MongoDB...")
        subprocess.run(
            ["mongorestore", f"--uri={settings.NORA_HOME_MONGO_URI}", f"--archive={archive}",
             "--gzip", "--drop"],
            check=True,
        )

    def _restore_media(self, root: Path):
        media = root / "media"
        if not media.exists():
            return
        self.stdout.write("Restoring media files...")
        shutil.copytree(media, Path(settings.MEDIA_ROOT), dirs_exist_ok=True)
