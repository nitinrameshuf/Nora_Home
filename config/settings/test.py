"""
Settings the test suite runs under, on any machine.

This module exists because `dev.py` was not actually hermetic. It layers on
`base.py`, which reads the database engine, the cache, and the installed house
apps from `.env` — so running the suite on the Pi picked up that machine's real
configuration and tried to create `test_nora_home` in MySQL, which the `nora`
user has no grant for. Every database test errored. On a laptop with a laptop
`.env`, the same command passed.

A test suite whose result depends on which machine it runs on is not a test
suite. Everything below is therefore pinned rather than read from the
environment:

  * SQLite, so no test can touch or need the real database;
  * the local-memory cache, so the settings store cannot reach for Redis;
  * the in-memory channel layer, so the display bus and the home bot are
    exercised for real instead of being swallowed by a missing layer;
  * eager Celery, so a queued task runs inline and its effects are assertable.

Nothing here should ever read `os.environ`. That is the whole point.

No house app is forced in here any more (there was one — houseapps.example_habit,
the old reference app — removed as part of the Levels/Todo work; see
docs/Main_App/subsystems/todo.md §1). Until a real family app exists
(Story 24), `tests/test_house_apps.py`'s contract tests legitimately run against
zero apps and its "at least one installed" guard skips rather than fails — see
the comment there for why that is the correct behaviour and not a silent gap.
"""

from __future__ import annotations

from .base import (  # noqa: F401
    DJANGO_APPS,
    NORA_HOME_HOUSE_APPS,
    NORA_HOME_PLATFORM_APPS,
    THIRD_PARTY_APPS,
)
from .dev import *  # noqa: F403

DEBUG = False  # closer to how the house actually serves pages
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    }
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

CELERY_BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_RESULT_BACKEND = "cache+memory://"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Object storage and Mongo are optional everywhere else in this codebase; in
# tests they are simply off, so nothing reaches for a socket.
NORA_HOME_MONGO_ENABLED = False
NORA_HOME_S3_ENABLED = False

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + NORA_HOME_PLATFORM_APPS + NORA_HOME_HOUSE_APPS

# Fast and deterministic: the real hasher is deliberately slow, and no test here
# depends on it. (The house has no passwords anyway — see CLAUDE.md §4.)
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# A test that fails because a template silently swallowed a bad variable is a
# test that lied. Make it loud instead.
TEMPLATES[0]["OPTIONS"]["debug"] = True  # noqa: F405
