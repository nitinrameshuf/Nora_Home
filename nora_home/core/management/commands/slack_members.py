"""
Match house members to Slack people, so the escalation ladder can DM them.

Personal notifications go to `HouseMember.slack_user_id`. Until it is set, every
personal alert falls back to the house channel — which works, but means a nudge
meant for one person is read by everyone, and the escalation ladder's whole
point (tell the owner first, quietly) is lost.

    manage.py slack_members                      # who is in Slack, who is linked
    manage.py slack_members --auto               # match on email, then on name
    manage.py slack_members --link nitin=U01ABC  # set one by hand
    manage.py slack_members --test nitin         # actually DM them

Needs the `users:read` scope (and `users:read.email` for email matching). See
.env.example for the full list of scopes this house uses.
"""

from __future__ import annotations

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

SLACK_USERS_LIST = "https://slack.com/api/users.list"
TIMEOUT = 20


class Command(BaseCommand):
    help = "Link house members to their Slack accounts so they can be DMed."

    def add_arguments(self, parser):
        parser.add_argument("--auto", action="store_true",
                            help="Link automatically where the match is unambiguous.")
        parser.add_argument("--link", action="append", default=[],
                            metavar="USERNAME=SLACK_ID",
                            help="Link one member by hand. Repeatable.")
        parser.add_argument("--test", metavar="USERNAME",
                            help="Send a real DM to one member, to prove it works.")

    def handle(self, *args, **options):
        from nora_home.accounts.models import HouseMember

        for pair in options["link"]:
            self._link_one(HouseMember, pair)
        if options["link"]:
            return

        if options["test"]:
            self._send_test(HouseMember, options["test"])
            return

        people = self._slack_people()
        if options["auto"]:
            self._auto_link(HouseMember, people)
        self._report(HouseMember, people)

    # ── Slack ─────────────────────────────────────────────────────────────────
    def _slack_people(self) -> list[dict]:
        token = settings.NORA_HOME_SLACK_BOT_TOKEN
        if not token:
            raise CommandError(
                "NORA_HOME_SLACK_BOT_TOKEN is not set. See .env.example.")

        people, cursor = [], ""
        while True:
            try:
                payload = requests.get(
                    SLACK_USERS_LIST,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"limit": 200, **({"cursor": cursor} if cursor else {})},
                    timeout=TIMEOUT,
                ).json()
            except requests.RequestException as exc:
                raise CommandError(f"Could not reach Slack: {exc}") from exc

            if not payload.get("ok"):
                error = payload.get("error", "?")
                if error == "missing_scope":
                    raise CommandError(
                        "The bot token lacks the `users:read` scope, so it cannot "
                        "list workspace members. Add it in the Slack app config, "
                        "reinstall the app, then run this again. You can still "
                        "link by hand with --link username=U01ABCDEF."
                    )
                raise CommandError(f"Slack refused users.list ({error}).")

            for user in payload.get("members", []):
                if user.get("deleted") or user.get("is_bot") or user["id"] == "USLACKBOT":
                    continue
                profile = user.get("profile", {})
                people.append({
                    "id": user["id"],
                    "name": user.get("name", ""),
                    "real_name": profile.get("real_name", ""),
                    "display_name": profile.get("display_name", ""),
                    "email": (profile.get("email") or "").lower(),
                })

            cursor = payload.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                return people

    # ── linking ───────────────────────────────────────────────────────────────
    def _link_one(self, HouseMember, pair: str):
        if "=" not in pair:
            raise CommandError(f"--link takes USERNAME=SLACK_ID, got {pair!r}")
        username, slack_id = (part.strip() for part in pair.split("=", 1))

        member = HouseMember.objects.filter(username=username).first()
        if member is None:
            raise CommandError(f"No house member called {username!r}.")

        member.slack_user_id = slack_id
        # Any cached DM conversation belonged to the previous id.
        member.slack_dm_channel = ""
        member.save(update_fields=["slack_user_id", "slack_dm_channel"])
        self.stdout.write(self.style.SUCCESS(f"Linked {username} -> {slack_id}"))

    def _auto_link(self, HouseMember, people: list[dict]):
        """Only link where exactly one Slack person matches. An ambiguous guess
        would quietly send someone else's reminders to the wrong person."""
        by_email = {p["email"]: p for p in people if p["email"]}
        linked = 0

        for member in HouseMember.objects.filter(is_active=True, slack_user_id=""):
            match = by_email.get((member.email or "").lower()) if member.email else None

            if match is None:
                wanted = {member.username.lower(),
                          (member.display_name or "").lower(),
                          member.get_full_name().lower()} - {""}
                candidates = [
                    p for p in people
                    if {p["name"].lower(), p["real_name"].lower(),
                        p["display_name"].lower()} & wanted
                ]
                if len(candidates) == 1:
                    match = candidates[0]
                elif len(candidates) > 1:
                    self.stdout.write(self.style.WARNING(
                        f"  {member.username}: {len(candidates)} possible Slack "
                        "matches; link by hand with --link"))

            if match:
                member.slack_user_id = match["id"]
                member.slack_dm_channel = ""
                member.save(update_fields=["slack_user_id", "slack_dm_channel"])
                self.stdout.write(self.style.SUCCESS(
                    f"  linked {member.username} -> {match['id']} "
                    f"({match['real_name'] or match['name']})"))
                linked += 1

        self.stdout.write(f"Linked {linked} member(s).")

    # ── reporting ─────────────────────────────────────────────────────────────
    def _report(self, HouseMember, people: list[dict]):
        self.stdout.write("\nSlack workspace:")
        for person in sorted(people, key=lambda p: p["real_name"] or p["name"]):
            label = person["real_name"] or person["display_name"] or person["name"]
            self.stdout.write(f"  {person['id']:<12} {label:<24} {person['email']}")

        self.stdout.write("\nHouse members:")
        unlinked = 0
        for member in HouseMember.objects.filter(is_active=True):
            if member.slack_user_id:
                self.stdout.write(f"  {member.username:<12} -> {member.slack_user_id} [ok]")
            else:
                unlinked += 1
                self.stdout.write(self.style.WARNING(
                    f"  {member.username:<12} -> not linked; personal alerts fall "
                    "back to the house channel"))

        if unlinked:
            self.stdout.write(
                "\nLink them with --auto, or --link username=U01ABCDEF, "
                "then check with --test username.")

    # ── proving it ────────────────────────────────────────────────────────────
    def _send_test(self, HouseMember, username: str):
        from nora_home.notifications.api import notify

        member = HouseMember.objects.filter(username=username).first()
        if member is None:
            raise CommandError(f"No house member called {username!r}.")
        if not member.slack_user_id:
            raise CommandError(
                f"{username} has no slack_user_id. Run this command with --auto, "
                "or --link, first.")

        notification = notify(
            member, title="Nora Home: direct message test",
            body="If you can read this, the house can reach you personally — "
                 "which is what the escalation ladder needs.",
            app_slug="core", channels=["slack"], sync=True,
        )
        delivery = notification.deliveries.get()

        if delivery.status == delivery.Status.SENT:
            self.stdout.write(self.style.SUCCESS(
                f"DM delivered to {username} ({delivery.target})."))
        else:
            self.stdout.write(self.style.ERROR(
                f"DM to {username} failed: {delivery.error}"))
