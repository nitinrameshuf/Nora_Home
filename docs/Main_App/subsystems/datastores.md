# Datastores — `nora_home.datastores`

## What it is

The two stores that sit alongside MySQL, and the backup/restore commands for all of
them.

- **MongoDB** — journals, AI transcripts, raw integration payloads. Anything whose
  shape changes without a migration.
- **Object storage (MinIO / S3)** — files, photos, exports, backups.

## Status

**Built, unproven.** Both helpers work; `nora_backup` / `nora_restore` have never
been run as a real disaster-recovery exercise.

## Models

None. This app holds no database tables — it is helpers plus management commands,
and exists as a `NoraAppConfig` only so it appears in the registry. It has no
`urls.py` and no page (`nora_has_page = False`), so it is correctly absent from the
Apps page.

## Both are optional

**The house runs degraded, not broken, without either.** Catch the unavailable
exception and carry on — a dead Mongo is "degraded", never "down". The wall display
must survive anything.

| Store | Exception | Enabled by |
|---|---|---|
| Mongo | `MongoUnavailable` | `NORA_HOME_MONGO_ENABLED` |
| Objects | `StorageUnavailable` | `NORA_HOME_S3_ENABLED` |

> A real instance of getting this wrong: `bootstrap_home` caught only
> `StorageUnavailable`, not the Pi's actual MinIO signature-mismatch error, so it
> silently killed everything after it — including integration seeding. Catch
> broadly when object storage is meant to be optional.

## Why three stores

| Store | For |
|---|---|
| **MySQL** | Anything the tracker joins across. The relational spine |
| **Mongo** | Documents whose shape will change. Optional |
| **Object storage** | Bytes. Optional |

See [`../../CLAUDE.md`](../../../CLAUDE.md) § 4.

## What it offers other apps

`nora_home.datastores.mongo` and `nora_home.datastores.objects`. Keys and
collections are namespaced by `app_slug` for you. Signatures in
[`../cross-functionality.md`](../cross-functionality.md#datastores).

For ordinary file uploads, prefer a normal Django `FileField` — it already routes
to object storage.

## Background work

| Task | Schedule | Does |
|---|---|---|
| `nightly_backup` | nightly | Dumps MySQL and Mongo, optionally to object storage, prunes by retention |

## Management commands

| Command | Does |
|---|---|
| `nora_backup` | Dump everything, now |
| `nora_restore` | Restore, including a cross-engine migration path (SQLite ↔ MySQL) |

## Settings

| Key | For |
|---|---|
| `NORA_HOME_MONGO_ENABLED` / `_URI` / `_DB` | Mongo |
| `NORA_HOME_S3_ENABLED` / `_ENDPOINT_URL` / `_BUCKET` / `_ACCESS_KEY` / `_SECRET_KEY` / `_REGION` / `_USE_SSL` | Object storage |
| `NORA_HOME_BACKUP_DIR` / `_RETAIN_DAYS` / `_TO_OBJECT_STORAGE` | Backups |

## Known gaps

- **A restore has never been rehearsed.** Backups that have not been restored are a
  hypothesis, not a backup.
- No tests (Story 21).

## Files

```
mongo.py     get_client, collection, put_document, ensure_indexes, ping
objects.py   put_bytes, get_bytes, put_file, presigned_url, delete, ensure_bucket
tasks.py     nightly_backup
management/commands/  nora_backup, nora_restore
```
