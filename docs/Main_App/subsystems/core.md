# Core — `nora_home.core`

## What it is

The spine everything else hangs off: the **app registry** that turns a Django app
into part of the house, the base model classes, the settings store, the audit
trail, and health.

## Status

**Complete.** The registry is exercised every request; health is on the wall.

## The app registry

`registry.py` is the most important file in the platform. A house app declares a
`NoraAppConfig` in its `apps.py`, and from that one class the platform derives its
URL mount, nav entry, dashboard widgets, wall panels, kiosk controls, MCP presence,
and minimum role. See [`../DEVELOPMENT.md`](../DEVELOPMENT.md) for the full
contract.

| Function | Does |
|---|---|
| `registered_apps(include_disabled=False)` | Every `NoraAppConfig`, sorted for display |
| `house_apps(include_disabled=False)` | Only apps the family wrote — what the Apps page shows |
| `navigation(role)` | The nav tree, grouped by category, filtered by role |
| `all_widgets(role)` | Every widget offered to the home screen |
| `scope_members(request)` | Who a widget's data should cover — honours the "Everyone" switcher |
| `house_app_urlpatterns()` | Mounts each app at its own top-level URL |

**`RESERVED_SLUGS`** stops a house app claiming a platform prefix. A broken app is
skipped at mount with a logged error rather than taking the house down.

> **If the nav and app directory ever go blank, look here first.** Django picks an
> app's config by inspecting `AppConfig` subclasses in `apps.py`; because that file
> also imports `NoraAppConfig` there are always two candidates, and with no
> tie-breaker Django quietly falls back to a plain `AppConfig` and the registry
> comes back empty. `default = False` on the base plus `__init_subclass__` marking
> real configs is what prevents it.

## Models

| Model | Holds |
|---|---|
| `TimeStampedModel` | `created_at` / `updated_at`. **Every model inherits at least this** |
| `OwnedModel` | Belongs to a `HouseMember` |
| `UUIDModel` | For anything referenced from outside the database |
| `SoftDeleteModel` | For anything losing would hurt |
| `HouseSetting` | Generic cached key/value house config, admin-editable |
| `AuditEvent` | Who did what, when |
| `SystemHealthSnapshot` | Periodic vitals, for the health chart |
| `DeviceToken` | Scoped tokens for machines — how the robot reads MCP |

## What it offers other apps

Base models, `core.signals` (see
[`../cross-functionality.md`](../cross-functionality.md#signals)),
`core.audit.record()`, `settings_store.get_setting()` / `set_setting()`, and
`registry.scope_members()`.

Widgets: `HouseHealthWidget`, `CpuTemperatureWidget`, `DiskWidget`.

## Background work

| Task | Schedule | Does |
|---|---|---|
| `record_health_snapshot` | every 10 min | Writes CPU, memory, disk, temperature |
| `prune_old_records` | periodic | Trims audit and snapshot history |

## Settings

Owns the `NORA_HOME_*` namespace in `config/settings/base.py`. **No app reads
`os.environ` directly** — add the setting there with a default and read it via
`django.conf.settings`.

`env_list()` deliberately does not go through `env()`: an explicitly empty value is
meaningful for a list (`NORA_HOME_HOUSE_APPS=` with no apps installed) where it
would be a mistake for a scalar. Getting this wrong made `uninstall_app` silently
undo itself on restart.

## Known gaps

- No tests (Story 21).
- `HouseSetting` has exactly one consumer today (the wall power schedule); the
  Settings page renders a plain form rather than a settings registry, deliberately,
  until there are enough to justify one.

## Files

```
registry.py       NoraAppConfig, AppMetadata, navigation, house_apps
models.py         base classes, HouseSetting, AuditEvent, DeviceToken
signals.py        the cross-app signal definitions
settings_store.py get_setting / set_setting, cached
health.py         collect_health()
audit.py          record()
cards.py          Card base class
views.py          dashboard, app directory, settings, status, health
management/commands/  bootstrap_home, install_app, uninstall_app, add_member, list_apps
```
