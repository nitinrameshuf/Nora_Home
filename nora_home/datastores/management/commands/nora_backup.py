"""
Back up everything the house knows.

    python manage.py nora_backup
    python manage.py nora_backup --to-object-storage --skip-media

Produces one timestamped directory containing:

    manifest.json     what this backup contains and what produced it
    sql/              mysqldump (or the sqlite file) — the relational core
    mongo/            mongodump archive — documents
    media/            uploaded files, when storage is local
    fixtures/         a portable JSON dump of the whole ORM

The fixtures dump is the migration path: it restores into a *different* database
engine, which is what makes moving off this Pi possible without a MySQL server on
the other end. The SQL dump is the fast, exact path for restoring the same setup.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Back up MySQL, MongoDB, media, and a portable ORM fixture."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Directory to write into.")
        parser.add_argument("--skip-mongo", action="store_true")
        parser.add_argument("--skip-media", action="store_true")
        parser.add_argument("--skip-fixtures", action="store_true")
        parser.add_argument("--compress", action="store_true",
                            help="Also produce a single .tar.gz.")
        parser.add_argument("--to-object-storage", action="store_true",
                            help="Upload the archive to MinIO/S3 when finished.")

    def handle(self, *args, **options):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        root = Path(options["output"] or settings.NORA_HOME_BACKUP_DIR) / f"nora-{stamp}"
        root.mkdir(parents=True, exist_ok=True)
        self.stdout.write(f"Backing up to {root}")

        manifest = {
            "created_at": datetime.now().isoformat(),
            "house": settings.NORA_HOME_NAME,
            "version": settings.NORA_HOME_VERSION,
            "environment": settings.NORA_HOME_ENV,
            "db_engine": settings.DATABASES["default"]["ENGINE"],
            "installed_apps": settings.NORA_HOME_PLATFORM_APPS + settings.NORA_HOME_HOUSE_APPS,
            "parts": {},
        }

        manifest["parts"]["sql"] = self._dump_sql(root)

        if not options["skip_fixtures"]:
            manifest["parts"]["fixtures"] = self._dump_fixtures(root)
        if not options["skip_mongo"]:
            manifest["parts"]["mongo"] = self._dump_mongo(root)
        if not options["skip_media"]:
            manifest["parts"]["media"] = self._copy_media(root)

        (root / "manifest.json").write_text(json.dumps(manifest, indent=2))

        archive = None
        if options["compress"] or options["to_object_storage"]:
            archive = self._compress(root)

        if options["to_object_storage"]:
            self._upload(archive)

        self._prune(root.parent)
        self.stdout.write(self.style.SUCCESS(f"Backup complete: {archive or root}"))

    # ── parts ──────────────────────────────────────────────────────────────────
    def _dump_sql(self, root: Path) -> dict:
        target = root / "sql"
        target.mkdir(exist_ok=True)
        db = settings.DATABASES["default"]

        if "sqlite" in db["ENGINE"]:
            shutil.copy2(db["NAME"], target / "db.sqlite3")
            return {"status": "ok", "kind": "sqlite", "file": "sql/db.sqlite3"}

        if shutil.which("mysqldump") is None:
            self.stderr.write("mysqldump not found; relying on the fixtures dump.")
            return {"status": "skipped", "reason": "mysqldump not installed"}

        out = target / "nora_home.sql"
        command = [
            "mysqldump", f"--host={db['HOST']}", f"--port={db['PORT']}",
            f"--user={db['USER']}", "--single-transaction", "--routines",
            "--triggers", "--default-character-set=utf8mb4", db["NAME"],
        ]
        env_password = {"MYSQL_PWD": db["PASSWORD"]} if db["PASSWORD"] else {}
        try:
            with out.open("wb") as handle:
                subprocess.run(command, stdout=handle, check=True, timeout=1800,
                               env={**dict(__import__("os").environ), **env_password})
        except subprocess.CalledProcessError as exc:
            raise CommandError(f"mysqldump failed with exit code {exc.returncode}")
        return {"status": "ok", "kind": "mysql", "file": "sql/nora.sql"}

    def _dump_fixtures(self, root: Path) -> dict:
        """Engine-independent JSON — the thing that makes migration possible."""
        target = root / "fixtures"
        target.mkdir(exist_ok=True)
        out = target / "all.json"
        try:
            with out.open("w", encoding="utf-8") as handle:
                call_command(
                    "dumpdata",
                    exclude=["contenttypes", "auth.permission", "sessions",
                             "admin.logentry", "django_celery_results"],
                    natural_foreign=True, natural_primary=True, indent=2,
                    stdout=handle,
                )
        except Exception as exc:
            self.stderr.write(f"Fixture dump failed: {exc}")
            return {"status": "failed", "error": str(exc)[:200]}
        return {"status": "ok", "file": "fixtures/all.json"}

    def _dump_mongo(self, root: Path) -> dict:
        if not settings.NORA_HOME_MONGO_ENABLED:
            return {"status": "skipped", "reason": "mongo disabled"}
        if shutil.which("mongodump") is None:
            return {"status": "skipped", "reason": "mongodump not installed"}

        target = root / "mongo"
        target.mkdir(exist_ok=True)
        archive = target / "nora_home.archive.gz"
        try:
            subprocess.run(
                ["mongodump", f"--uri={settings.NORA_HOME_MONGO_URI}",
                 f"--db={settings.NORA_HOME_MONGO_DB}", f"--archive={archive}", "--gzip"],
                check=True, timeout=1800, capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            self.stderr.write(f"mongodump failed: {exc.stderr[:300]!r}")
            return {"status": "failed"}
        return {"status": "ok", "file": "mongo/nora.archive.gz"}

    def _copy_media(self, root: Path) -> dict:
        if settings.NORA_HOME_S3_ENABLED:
            return {"status": "skipped",
                    "reason": "media lives in object storage; back the bucket up there"}
        media = Path(settings.MEDIA_ROOT)
        if not media.exists():
            return {"status": "skipped", "reason": "no media directory"}
        shutil.copytree(media, root / "media", dirs_exist_ok=True)
        return {"status": "ok", "path": "media/"}

    # ── packaging ──────────────────────────────────────────────────────────────
    def _compress(self, root: Path) -> Path:
        archive = root.with_suffix(".tar.gz")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(root, arcname=root.name)
        shutil.rmtree(root)
        self.stdout.write(f"Compressed to {archive}")
        return archive

    def _upload(self, archive: Path | None):
        if archive is None:
            self.stderr.write("Nothing to upload.")
            return
        from nora_home.datastores.objects import StorageUnavailable, put_file

        try:
            key = put_file(f"backups/{archive.name}", archive, app_slug="system")
        except StorageUnavailable as exc:
            self.stderr.write(f"Could not upload backup: {exc}")
            return
        self.stdout.write(f"Uploaded to object storage as {key}")

    def _prune(self, directory: Path):
        """Old backups fill an SD card quietly. Keep the retention window only."""
        keep_days = settings.NORA_HOME_BACKUP_RETAIN_DAYS
        if not keep_days:
            return
        cutoff = datetime.now().timestamp() - keep_days * 86400
        for entry in directory.glob("nora-*"):
            if entry.stat().st_mtime < cutoff:
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
                self.stdout.write(f"Pruned old backup {entry.name}")
