"""
Set up a fresh house.

    python manage.py bootstrap_home
    python manage.py bootstrap_home --demo

Creates the escalation policies, the two displays, and the object-storage bucket.
With --demo it also creates a family, some habits, and a few measurements, so the
dashboard and wall display have something real to render on the first run.

Safe to run repeatedly — everything is get_or_create.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

DEFAULT_POLICIES = [
    {
        "name": "House default",
        "description": "Nudge, warn, tell the household, then tell everyone.",
        "grace_minutes": 15,
        "is_default": True,
        "levels": [
            {"after_minutes": 0, "notify": "owner", "severity": "nudge"},
            {"after_minutes": 120, "notify": "owner", "severity": "warning"},
            {"after_minutes": 720, "notify": "chain", "severity": "alert"},
            {"after_minutes": 2880, "notify": "house", "severity": "critical"},
        ],
    },
    {
        "name": "Gentle",
        "description": "For habits. One nudge, one reminder, then let it go.",
        "grace_minutes": 60,
        "levels": [
            {"after_minutes": 0, "notify": "owner", "severity": "info"},
            {"after_minutes": 480, "notify": "owner", "severity": "nudge"},
        ],
    },
    {
        "name": "Safety critical",
        "description": "Smoke alarms, medication, the boiler. Escalates fast and hard.",
        "grace_minutes": 0,
        "levels": [
            {"after_minutes": 0, "notify": "owner", "severity": "warning"},
            {"after_minutes": 15, "notify": "adults", "severity": "alert"},
            {"after_minutes": 60, "notify": "house", "severity": "critical"},
        ],
    },
]


class Command(BaseCommand):
    help = "Create the baseline records a new Nora Home install needs."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true",
                            help="Also create a demo family and sample data.")

    def handle(self, *args, **options):
        self._policies()
        self._displays()
        self._storage()
        if options["demo"]:
            self._demo()
        self.stdout.write(self.style.SUCCESS("The house is ready."))

    def _policies(self):
        from nora_home.tracker.models import EscalationPolicy

        for spec in DEFAULT_POLICIES:
            _, created = EscalationPolicy.objects.get_or_create(
                name=spec["name"], defaults=spec)
            self.stdout.write(f"  policy {spec['name']}: "
                              f"{'created' if created else 'already there'}")

    def _displays(self):
        from nora_home.displays.models import Display

        for slug, name, kind, size in [
            (settings.NORA_HOME_MAIN_DISPLAY_SLUG, "Wall display", Display.Kind.WALL,
             (1920, 1080)),
            (settings.NORA_HOME_KIOSK_DISPLAY_SLUG, "Kiosk", Display.Kind.KIOSK,
             (1280, 800)),
        ]:
            _, created = Display.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "kind": kind,
                          "width": size[0], "height": size[1],
                          "rotation_seconds": settings.NORA_HOME_DISPLAY_ROTATE_SECONDS,
                          "rotation_enabled": kind == Display.Kind.WALL},
            )
            self.stdout.write(f"  display {slug}: "
                              f"{'created' if created else 'already there'}")

    def _storage(self):
        from nora_home.datastores.objects import StorageUnavailable, ensure_bucket

        try:
            created = ensure_bucket()
        except StorageUnavailable as exc:
            self.stdout.write(f"  object storage: skipped ({exc})")
            return

        if created is None:
            self.stdout.write("  object storage: off -- uploads go to MEDIA_ROOT")
            return
        self.stdout.write(f"  bucket {settings.NORA_HOME_S3_BUCKET}: "
                          f"{'created' if created else 'already there'}")

    def _demo(self):
        from datetime import time

        from houseapps.example_habit.models import Habit
        from nora_home.accounts.models import EscalationContact, HouseMember
        from nora_home.telemetry.api import define_series, record_reading

        self.stdout.write("Creating demo data...")

        people = [
            ("nitin", "Nitin", HouseMember.Role.ADMIN),
            ("partner", "Partner", HouseMember.Role.ADULT),
            ("kid", "Kid", HouseMember.Role.MEMBER),
        ]
        members = {}
        for username, display_name, role in people:
            member, created = HouseMember.objects.get_or_create(
                username=username,
                defaults={"display_name": display_name, "role": role,
                          "is_staff": role == HouseMember.Role.ADMIN,
                          "is_superuser": role == HouseMember.Role.ADMIN},
            )
            if created:
                member.set_password("nora")  # demo only; change it immediately
                member.save()
            members[username] = member
            self.stdout.write(f"  member {username}: "
                              f"{'created (password: nora)' if created else 'exists'}")

        EscalationContact.objects.get_or_create(
            member=members["kid"], contact=members["nitin"],
            defaults={"level": 1, "note": "Parent"})

        habits = [
            ("nitin", "Twenty minutes of reading", "Because the phone wins otherwise",
             time(21, 0)),
            ("nitin", "Walk after lunch", "My back", time(13, 30)),
            ("kid", "Practice piano", "Recital in March", time(17, 0)),
        ]
        for username, title, why, due in habits:
            _, created = Habit.objects.get_or_create(
                owner=members[username], title=title,
                defaults={"why": why, "due_time": due, "cadence": Habit.Cadence.DAILY},
            )
            if created:
                self.stdout.write(f"  habit {title}")

        define_series("nora_home.battery", "Nora battery", unit="%", app_slug="robot",
                      alert_below=15, warn_below=30, direction="up",
                      show_on_wall=True)
        define_series("house.living_room.temp", "Living room", unit="°C",
                      app_slug="house", warn_below=17, warn_above=26,
                      direction="range", show_on_wall=True)

        record_reading("nora_home.battery", 87.0, source="robot")
        record_reading("house.living_room.temp", 21.4, source="integration")
        self.stdout.write("  telemetry seeded")
