"""What is installed in this house, and where each app lives."""

from django.core.management.base import BaseCommand

from nora_home.core.registry import registered_apps


class Command(BaseCommand):
    help = "List every app registered with the platform."

    def handle(self, *args, **options):
        apps = registered_apps(include_disabled=True)
        if not apps:
            self.stdout.write("No apps registered.")
            return

        width = max(len(a.title) for a in apps)
        for app in apps:
            flags = []
            if app.is_platform:
                flags.append("platform")
            if not app.enabled:
                flags.append("disabled")
            if app.widgets:
                flags.append(f"{len(app.widgets)} widgets")
            if app.provides_mcp_tools:
                flags.append("mcp")

            self.stdout.write(
                f"{app.title:<{width}}  /{app.url_prefix:<18}  {app.module}"
                + (f"  [{', '.join(flags)}]" if flags else "")
            )
