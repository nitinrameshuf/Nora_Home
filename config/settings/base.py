"""
Nora Home — base settings.

Everything configurable lives in the environment (see .env.example). Settings modules
layer on top of this one: config.settings.dev, config.settings.pi, config.settings.prod.

Rule for app authors: never read os.environ directly in an app. Add the setting here
with a sane default, then read it via django.conf.settings.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")


# ── env helpers ────────────────────────────────────────────────────────────────
def env(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key)
    return default if value is None or value == "" else value


def env_bool(key: str, default: bool = False) -> bool:
    raw = env(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    raw = env(key)
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


def env_list(key: str, default: list[str] | None = None) -> list[str]:
    # Deliberately doesn't go through env() above: env() treats "" the same as
    # unset, which is right for scalars (an accidentally-blank secret or host
    # shouldn't silently disappear) but wrong here — an explicitly empty list
    # is a real, meaningful config (e.g. NORA_HOME_HOUSE_APPS= with no house
    # apps installed), not a mistake to paper over. uninstall_app writes
    # exactly that line when the last house app comes out, so this has to be
    # able to mean "empty," not just "give me the default back."
    if key not in os.environ:
        return list(default or [])
    return [item.strip() for item in os.environ[key].split(",") if item.strip()]


def env_float(key: str, default: float | None) -> float | None:
    raw = env(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# ── Identity ───────────────────────────────────────────────────────────────────
NORA_HOME_ENV = env("NORA_HOME_ENV", "dev")
NORA_HOME_NAME = env("NORA_HOME_NAME", "Nora Home")
NORA_HOME_VERSION = "0.1.0"

SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-dev-key-replace-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])
# "*" means every host is trusted (the Pi's own LAN-is-the-boundary model — see
# CLAUDE.md §4, "Passwordless everywhere"); Django has no origin syntax for that,
# so skip it here rather than emit "http://*", which Django's CSRF check rejects.
CSRF_TRUSTED_ORIGINS = [
    f"http://{host}" for host in ALLOWED_HOSTS if host != "*" and not host.startswith(".")
] + [f"https://{host}" for host in ALLOWED_HOSTS if host != "*" and not host.startswith(".")]


# ── Applications ───────────────────────────────────────────────────────────────
DJANGO_APPS = [
    "daphne",  # must precede staticfiles so runserver speaks ASGI
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.humanize",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_filters",
    "channels",
    "django_celery_beat",
    "django_celery_results",
]

# Platform apps. These are the skeleton — house apps build on top of them.
NORA_HOME_PLATFORM_APPS = [
    "nora_home.core",
    "nora_home.dashboard",
    "nora_home.accounts",
    "nora_home.notifications",
    "nora_home.tracker",
    "nora_home.todo",
    "nora_home.ai",
    "nora_home.mcpserver",
    "nora_home.datastores",
    "nora_home.displays",
    "nora_home.telemetry",
    "nora_home.integrations",
    "nora_home.ui",
]

# House apps. Anything a family member deploys goes in houseapps/ and gets listed here
# (or in NORA_HOME_HOUSE_APPS in the environment, so a new app needs no code change).
# Empty by default: houseapps.example_habit (the old reference app) was removed as
# part of the Levels/Todo work (docs/Main_App/subsystems/todo.md §1) — the next
# entry here will be the first real family app (Story 24).
NORA_HOME_HOUSE_APPS = env_list("NORA_HOME_HOUSE_APPS", [])

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + NORA_HOME_PLATFORM_APPS + NORA_HOME_HOUSE_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "nora_home.core.middleware.RequestContextMiddleware",
    "nora_home.ui.middleware.SurfaceMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "nora_home.core.context_processors.house",
                "nora_home.ui.context_processors.surface",
                "nora_home.ui.context_processors.scene",
            ],
        },
    },
]


# ── Relational database ────────────────────────────────────────────────────────
if env("NORA_HOME_DB_ENGINE", "sqlite") == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": env("NORA_HOME_DB_NAME", "nora_home"),
            "USER": env("NORA_HOME_DB_USER", "nora"),
            "PASSWORD": env("NORA_HOME_DB_PASSWORD", ""),
            "HOST": env("NORA_HOME_DB_HOST", "127.0.0.1"),
            "PORT": env("NORA_HOME_DB_PORT", "3306"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {
                "charset": "utf8mb4",
                # STRICT_TRANS_TABLES turns silent truncation into an error.
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 20},
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.HouseMember"


# ── MongoDB ────────────────────────────────────────────────────────────────────
# Not a Django database backend. Reached through nora_home.datastores.mongo.collection().
NORA_HOME_MONGO_URI = env("NORA_HOME_MONGO_URI", "mongodb://127.0.0.1:27017")
NORA_HOME_MONGO_DB = env("NORA_HOME_MONGO_DB", "nora_home")
NORA_HOME_MONGO_ENABLED = env_bool("NORA_HOME_MONGO_ENABLED", True)


# ── Redis: cache, channels layer, locks ────────────────────────────────────────
NORA_HOME_REDIS_URL = env("NORA_HOME_REDIS_URL", "redis://127.0.0.1:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": NORA_HOME_REDIS_URL,
        "KEY_PREFIX": "nora",
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [NORA_HOME_REDIS_URL]},
    }
}


# ── Celery: RabbitMQ broker, Redis results ─────────────────────────────────────
# RabbitMQ handles the work queues (durable, good routing). Redis holds results and
# the cache. Flip NORA_HOME_BROKER_USE_REDIS=1 to run without RabbitMQ on a laptop.
if env_bool("NORA_HOME_BROKER_USE_REDIS", False):
    CELERY_BROKER_URL = NORA_HOME_REDIS_URL
else:
    CELERY_BROKER_URL = env("NORA_HOME_AMQP_URL", "amqp://nora:nora@127.0.0.1:5672//")

CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "django-cache"
CELERY_TIMEZONE = env("DJANGO_TIME_ZONE", "America/Los_Angeles")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_TIME_LIMIT = 60 * 15
CELERY_TASK_SOFT_TIME_LIMIT = 60 * 13
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # the Pi has 4 cores; keep queues fair
CELERY_WORKER_MAX_TASKS_PER_CHILD = 200
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_RESULT_EXTENDED = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Queues. House apps should use "apps"; the platform keeps its own lanes so a runaway
# app task never delays an escalation.
CELERY_TASK_DEFAULT_QUEUE = "apps"
NORA_HOME_CELERY_QUEUES = ["apps", "platform", "alerts", "ai", "integrations"]


# ── Object storage ─────────────────────────────────────────────────────────────
NORA_HOME_S3_ENABLED = env_bool("NORA_HOME_S3_ENABLED", False)
NORA_HOME_S3_BUCKET = env("NORA_HOME_S3_BUCKET", "nora-home")
NORA_HOME_S3_ENDPOINT_URL = env("NORA_HOME_S3_ENDPOINT_URL", "http://127.0.0.1:9000")
NORA_HOME_S3_ACCESS_KEY = env("NORA_HOME_S3_ACCESS_KEY", "")
NORA_HOME_S3_SECRET_KEY = env("NORA_HOME_S3_SECRET_KEY", "")
NORA_HOME_S3_REGION = env("NORA_HOME_S3_REGION", "us-east-1")
NORA_HOME_S3_USE_SSL = env_bool("NORA_HOME_S3_USE_SSL", False)

if NORA_HOME_S3_ENABLED:
    _default_file_storage = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": NORA_HOME_S3_BUCKET,
            "endpoint_url": NORA_HOME_S3_ENDPOINT_URL,
            "access_key": NORA_HOME_S3_ACCESS_KEY,
            "secret_key": NORA_HOME_S3_SECRET_KEY,
            "region_name": NORA_HOME_S3_REGION,
            "use_ssl": NORA_HOME_S3_USE_SSL,
            "addressing_style": "path",  # MinIO
            "file_overwrite": False,
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": 3600,
        },
    }
else:
    _default_file_storage = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

STORAGES = {
    "default": _default_file_storage,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}


# ── Slack ──────────────────────────────────────────────────────────────────────
NORA_HOME_SLACK_BOT_TOKEN = env("NORA_HOME_SLACK_BOT_TOKEN", "")
# App-level token (xapp-…, scope connections:write), a different credential from
# the bot token above. Only the Socket Mode process reads it — see
# nora_home.notifications.slack_socket for why the house dials out at all.
NORA_HOME_SLACK_APP_TOKEN = env("NORA_HOME_SLACK_APP_TOKEN", "")
NORA_HOME_SLACK_WEBHOOK_URL = env("NORA_HOME_SLACK_WEBHOOK_URL", "")
NORA_HOME_SLACK_DEFAULT_CHANNEL = env("NORA_HOME_SLACK_DEFAULT_CHANNEL", "#nora-home")
NORA_HOME_SLACK_ESCALATION_CHANNEL = env("NORA_HOME_SLACK_ESCALATION_CHANNEL", "#nora-home-alerts")

# Ordered channel backends. notify() walks them in order for each recipient.
NORA_HOME_NOTIFICATION_CHANNELS = {
    "slack": "nora_home.notifications.channels.slack.SlackChannel",
    "inapp": "nora_home.notifications.channels.inapp.InAppChannel",
    "display": "nora_home.notifications.channels.display.DisplayChannel",
    "console": "nora_home.notifications.channels.console.ConsoleChannel",
    "sound": "nora_home.notifications.channels.sound.SoundChannel",
}
NORA_HOME_NOTIFICATION_DEFAULT_CHANNELS = env_list(
    "NORA_HOME_NOTIFICATION_DEFAULT_CHANNELS", ["inapp", "slack"]
)


# ── AI ─────────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")
NORA_HOME_AI_MODEL = env("NORA_HOME_AI_MODEL", "claude-sonnet-5")
NORA_HOME_AI_FAST_MODEL = env("NORA_HOME_AI_FAST_MODEL", "claude-haiku-4-5")
NORA_HOME_AI_DEEP_MODEL = env("NORA_HOME_AI_DEEP_MODEL", "claude-opus-5")
NORA_HOME_AI_EFFORT = env("NORA_HOME_AI_EFFORT", "high")
NORA_HOME_AI_MAX_TOKENS = env_int("NORA_HOME_AI_MAX_TOKENS", 4096)
NORA_HOME_AI_MONTHLY_BUDGET_USD = env_int("NORA_HOME_AI_MONTHLY_BUDGET_USD", 25)
NORA_HOME_AI_ENABLED = bool(ANTHROPIC_API_KEY)


# ── MCP ────────────────────────────────────────────────────────────────────────
NORA_HOME_MCP_ENABLED = env_bool("NORA_HOME_MCP_ENABLED", True)
NORA_HOME_MCP_TOKEN = env("NORA_HOME_MCP_TOKEN", "")


# ── Displays ───────────────────────────────────────────────────────────────────
NORA_HOME_MAIN_DISPLAY_SLUG = env("NORA_HOME_MAIN_DISPLAY_SLUG", "wall")
NORA_HOME_KIOSK_DISPLAY_SLUG = env("NORA_HOME_KIOSK_DISPLAY_SLUG", "kiosk")


# ── Location ───────────────────────────────────────────────────────────────────
# Drives the weather integration and the living background's season/day-night
# axes (nora_home/ui/scene.py). Defaults to New York City, matching this house's
# DJANGO_TIME_ZONE default — correct it in .env for the house's real location.
NORA_HOME_LAT = env_float("NORA_HOME_LAT", 40.7128)
NORA_HOME_LON = env_float("NORA_HOME_LON", -74.0060)


# ── Backups ────────────────────────────────────────────────────────────────────
NORA_HOME_BACKUP_DIR = Path(env("NORA_HOME_BACKUP_DIR", str(BASE_DIR / "backups")))
# Where a resolved alarm's audio bytes land so the host-side player can reach
# them — Django runs in Docker and has no path to the physical speakers, same
# boundary the wall power schedule crosses (see docker-compose.yml's bind mount
# and scripts/lib/provision-pi.sh). Not used on a laptop; writes still succeed,
# there is simply nothing on the other end to play them.
NORA_HOME_ALARM_CACHE_DIR = Path(env("NORA_HOME_ALARM_CACHE_DIR", str(BASE_DIR / "var" / "alarms")))
NORA_HOME_BACKUP_RETAIN_DAYS = env_int("NORA_HOME_BACKUP_RETAIN_DAYS", 30)
NORA_HOME_BACKUP_TO_OBJECT_STORAGE = env_bool("NORA_HOME_BACKUP_TO_OBJECT_STORAGE", False)


# ── i18n / static / media ──────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", "America/Los_Angeles")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ── Auth ───────────────────────────────────────────────────────────────────────
# No password gates anything in this house — tap a name in the switcher instead.
# See docs/progress.md and CLAUDE.md §4 ("Passwordless everywhere").
LOGIN_URL = "/accounts/switch/"
LOGIN_REDIRECT_URL = "/home/"
LOGOUT_REDIRECT_URL = "/accounts/switch/"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # a month; this is a house, not a bank
SESSION_SAVE_EVERY_REQUEST = True
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]


# ── DRF ────────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "nora_home.core.api.auth.DeviceTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}


# ── Logging ────────────────────────────────────────────────────────────────────
NORA_HOME_LOG_DIR = Path(env("NORA_HOME_LOG_DIR", str(BASE_DIR / "logs")))
NORA_HOME_LOG_DIR.mkdir(parents=True, exist_ok=True)
NORA_HOME_LOG_LEVEL = env("NORA_HOME_LOG_LEVEL", "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname:<7} {name:<28} {message}",
            "style": "{",
        },
        "json": {"()": "nora_home.core.logging.JSONFormatter"},
    },
    "filters": {
        "request_context": {"()": "nora_home.core.logging.RequestContextFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["request_context"],
        },
        "file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": str(NORA_HOME_LOG_DIR / "nora_home.log"),
            "when": "midnight",
            "backupCount": 14,
            "encoding": "utf-8",
            "formatter": "json",
            "filters": ["request_context"],
        },
        "errors": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": str(NORA_HOME_LOG_DIR / "errors.log"),
            "when": "midnight",
            "backupCount": 30,
            "encoding": "utf-8",
            "level": "ERROR",
            "formatter": "json",
            "filters": ["request_context"],
        },
    },
    "root": {"handlers": ["console", "file", "errors"], "level": NORA_HOME_LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "propagate": True},
        "nora_home": {"level": NORA_HOME_LOG_LEVEL, "propagate": True},
        "houseapps": {"level": NORA_HOME_LOG_LEVEL, "propagate": True},
        "celery": {"level": "INFO", "propagate": True},
    },
}

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"
X_FRAME_OPTIONS = "SAMEORIGIN"
