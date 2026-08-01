"""
Add a household member. There is no password anywhere in this house — everyone
signs in by tapping their name in the switcher — so this deliberately does not use
Django's createsuperuser, which would make every member a superuser regardless of
the role you actually want them to have.

    python manage.py add_member nitin --display-name Nitin --role admin
"""

from django.core.management.base import BaseCommand, CommandError

from nora_home.accounts.models import HouseMember


class Command(BaseCommand):
    help = "Create a house member with an explicit role. No password is set."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--display-name", default="", help="Shown in the switcher.")
        parser.add_argument("--role", default=HouseMember.Role.MEMBER,
                            choices=[c[0] for c in HouseMember.Role.choices],
                            help="member (default), adult, or admin.")

    def handle(self, *args, **options):
        username = options["username"]
        if HouseMember.objects.filter(username=username).exists():
            raise CommandError(f"{username!r} already exists.")

        member = HouseMember(username=username,
                             display_name=options["display_name"],
                             role=options["role"])
        member.set_unusable_password()
        member.save()

        self.stdout.write(self.style.SUCCESS(
            f"Added {member.name} as {member.role}. No password set — "
            f"they sign in by tapping their name in the switcher."))
        if member.role == HouseMember.Role.ADMIN:
            self.stdout.write("This role reaches /admin/ with no password prompt.")
