"""
Issue a long-lived token for a non-browser client — the robot, a phone shortcut,
a script.

    python manage.py issue_device_token "Nora robot" --member nitin --scopes read,write

The plaintext token is printed once and never stored; only its hash is kept, so a
leaked database does not leak working credentials.
"""

from django.core.management.base import BaseCommand, CommandError

from nora_home.core.api.auth import generate_token
from nora_home.core.models import DeviceToken


class Command(BaseCommand):
    help = "Create a device token. The plaintext is shown once."

    def add_arguments(self, parser):
        parser.add_argument("name", help="What this token is for.")
        parser.add_argument("--member", help="Username this device acts as.")
        parser.add_argument("--scopes", default="read",
                            help="Comma-separated: read, write, telemetry:write.")

    def handle(self, *args, **options):
        from nora_home.accounts.models import HouseMember

        member = None
        if options["member"]:
            member = HouseMember.objects.filter(username=options["member"]).first()
            if member is None:
                raise CommandError(f"No member called {options['member']!r}.")
        else:
            member = HouseMember.objects.filter(is_superuser=True).first()
            if member is None:
                raise CommandError(
                    "No member given and no superuser exists to bind the token to. "
                    "Pass --member."
                )

        plaintext, prefix, digest = generate_token()
        scopes = [s.strip() for s in options["scopes"].split(",") if s.strip()]

        DeviceToken.objects.create(name=options["name"], token_hash=digest,
                                   prefix=prefix, member=member, scopes=scopes)

        self.stdout.write(self.style.SUCCESS(f"\nToken for {options['name']}:"))
        self.stdout.write(f"\n    {plaintext}\n")
        self.stdout.write(f"Acting as: {member}   Scopes: {', '.join(scopes)}")
        self.stdout.write(self.style.WARNING(
            "This is the only time it will be shown. Store it now."))
        self.stdout.write("\nUse it as:  Authorization: Bearer <token>")
