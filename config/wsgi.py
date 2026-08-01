"""WSGI entrypoint — used by gunicorn when websockets are handled separately."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.pi")

application = get_wsgi_application()
