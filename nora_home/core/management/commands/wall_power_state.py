"""
Decides whether the 24" wall display should be powered on or off right now.

    python manage.py wall_power_state

Prints exactly "on" or "off" to stdout and nothing else, so a plain host-side
script (outside Docker, where the actual monitor lives) can act on it without
reimplementing the schedule or timezone logic in bash:

    STATE=$(docker compose exec -T web python manage.py wall_power_state)
    xset -display :0 dpms force "$STATE"

The decision lives here, in Django, deliberately — this is the one place
that already knows the house's timezone and already has a settings store.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from nora_home.core.views import WALL_SCHEDULE_DEFAULT, WALL_SCHEDULE_KEY


class Command(BaseCommand):
    help = "Print 'on' or 'off' — whether the wall display should be powered right now."

    def handle(self, *args, **options):
        from nora_home.core.settings_store import get_setting

        schedule = get_setting(WALL_SCHEDULE_KEY, default=WALL_SCHEDULE_DEFAULT)
        if not schedule.get("enabled"):
            self.stdout.write("on")
            return

        hour = timezone.localtime().hour
        start = int(schedule.get("start_hour", 9))
        end = int(schedule.get("end_hour", 20))
        in_off_window = start <= hour < end if start <= end else start <= hour or hour < end

        self.stdout.write("off" if in_off_window else "on")
