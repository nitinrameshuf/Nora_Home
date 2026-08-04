# Accounts — `nora_home.accounts`

## What it is

Who lives here, what they may see, how to reach them, and who hears about it when
they forget something. `HouseMember` is `AUTH_USER_MODEL`.

## Status

**Complete.** Passwordless switching is used on every surface daily.

## Models

| Model | Holds |
|---|---|
| `HouseMember` | name, username, role, Slack ID, quiet hours, notification prefs, whether they appear on the wall |
| `EscalationContact` | An ordered chain: who to tell next when this person doesn't do something |

Roles: `member`, `adult`, `admin`. `nora_minimum_role` on an app is checked against
these, so a kid simply does not see an app that isn't for them.

`HouseMember.save()` forces `is_staff` / `is_superuser` from `role == admin`, so an
admin reaches `/admin/` with no separate gate to keep in sync.

## Passwordless, everywhere, on purpose

**There is no password anywhere in this system, on any surface** — phone, laptop,
wall, kiosk, or `/admin/`. A topbar switcher lists the household; tapping a name
logs you in as them via `django.contrib.auth.login()` with no password check.

This was a deliberate decision, not an oversight, and it is written up in
[`../../CLAUDE.md`](../../../CLAUDE.md) § 4: the house LAN is already the trust
boundary everywhere else in the system (Slack tokens, MCP device tokens, secrets
all live at that boundary, not per-request), and a family member — including a kid
— should not need a password for an always-on wall display.

A third tile, **Everyone**, switches to a combined household view
(`DashboardLayout.Surface.SHARED`), which widgets pick up for free via
`registry.scope_members(request)`.

> `make member` runs `add_member` (unusable password, explicit `--role`), **not**
> Django's `createsuperuser` — which used to make every house member a superuser
> regardless of role. Harmless while a password gated `/admin/`; not once it
> doesn't.

## What it offers other apps

`settings.AUTH_USER_MODEL` for any `ForeignKey` to a person, and
`member.escalation_chain()`. Do not build your own idea of a user.

## Background work

None.

## Settings

None of its own.

## Known gaps

- No tests (Story 21).
- The old `/accounts/me/` profile page was folded into **Settings**; the route
  remains as a redirect so existing links still land.

## Files

```
models.py   HouseMember, EscalationContact
views.py    switch picker, switch_to, switch_to_everyone, logout, household
urls.py     mounted at /accounts/
```

Templates: `accounts/switch.html`, `accounts/household.html`. The profile card now
lives in `core/settings.html`.
