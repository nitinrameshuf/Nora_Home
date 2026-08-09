"""A minimal house app, declared exactly as DEVELOPMENT.md tells an author to.

It exists so the platform's promise to app authors is executable rather than
written down and hoped for. See tests/test_app_contract.py.

Deliberately has no models: it is installed mid-test via override_settings,
and Django will not run migrations for an app added after the test database
was built. Everything the contract actually covers — nav, sections, widgets,
kiosk controls, URLs — needs no tables.
"""
