"""The declaration. Every line here is something DEVELOPMENT.md tells an author
to write, and every line is asserted by tests/test_app_contract.py."""

from __future__ import annotations

from nora_home.core.registry import Category, NoraAppConfig


class ContractAppConfig(NoraAppConfig):
    name = "tests.contract_app"
    label = "contract_app"
    verbose_name = "Contract App"

    nora_slug = "contractapp"
    nora_title = "Contract App"
    nora_description = "A house app that exists only to prove the contract holds."
    nora_category = Category.HOUSE
    nora_url_prefix = "contractapp/"
    nora_has_page = True
    nora_nav = True

    nora_widgets = ["tests.contract_app.widgets.ContractStatWidget"]

    nora_sections = [
        {"title": "Overview", "path": "/contractapp/"},
        {"title": "History", "path": "/contractapp/history/"},
    ]

    nora_kiosk_controls = [
        {"title": "Overview", "path": "/contractapp/"},
        {"title": "History", "path": "/contractapp/history/"},
    ]
