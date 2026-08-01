"""Laptop development. SQLite, local memory cache, eager Celery if you want it."""

from .base import *  # noqa: F403
from .base import INSTALLED_APPS, NORA_HOME_REDIS_URL, env_bool

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Redis is optional on a laptop — fall back to in-process equivalents when it is down.
if not env_bool("NORA_HOME_DEV_USE_REDIS", False):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    CELERY_BROKER_URL = "memory://"
else:
    CELERY_BROKER_URL = NORA_HOME_REDIS_URL

# Run tasks inline so `runserver` alone is a working system.
CELERY_TASK_ALWAYS_EAGER = env_bool("NORA_HOME_CELERY_EAGER", True)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_BEAT_SCHEDULER = "celery.beat:PersistentScheduler"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Nice to have, not required — someone who installed only requirements/base.txt
# should still be able to run the dev server.
try:
    import django_extensions  # noqa: F401
except ImportError:
    pass
else:
    INSTALLED_APPS = [*INSTALLED_APPS, "django_extensions"]
