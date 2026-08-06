"""
Hold the Socket Mode websocket open. This is what the `slack` container runs.

    python manage.py slack_socket          # connect and block
    python manage.py slack_socket --check  # report configuration and exit

`--check` exists because the failure this guards against is silent: a container
that starts, finds no app token, and sits there looking healthy. Run it after
editing .env to get a straight answer before restarting anything.
"""

from django.core.management.base import BaseCommand, CommandError

from nora_home.notifications import slack_socket
from nora_home.notifications.slack_commands import registered_actions, registered_commands


class Command(BaseCommand):
    help = "Run the Slack Socket Mode listener (slash commands and buttons)."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true",
                            help="Report whether Slack is configured, then exit.")

    def handle(self, *args, **options):
        if options["check"]:
            configured = slack_socket.is_configured()
            self.stdout.write(f"configured: {configured}")
            self.stdout.write(f"commands:   {', '.join(registered_commands()) or '(none)'}")
            self.stdout.write(f"actions:    {', '.join(registered_actions()) or '(none)'}")
            if not configured:
                raise CommandError(
                    "Socket Mode needs NORA_HOME_SLACK_APP_TOKEN and "
                    "NORA_HOME_SLACK_BOT_TOKEN. See .env.example.")
            return

        try:
            slack_socket.run_forever()
        except slack_socket.SlackSocketNotConfigured as exc:
            raise CommandError(str(exc)) from exc
