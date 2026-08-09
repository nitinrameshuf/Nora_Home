"""One widget, written the way DEVELOPMENT.md tells an app author to write one.

Subclasses StatWidget and implements stat() — nothing more. If the widget base
class ever changes shape, this stops loading and the contract test says so.
"""

from __future__ import annotations

from nora_home.dashboard.widgets import StatWidget


class ContractStatWidget(StatWidget):
    title = "Contract stat"
    description = "Proof that a declared widget is pickable and renders."

    def stat(self, request):  # noqa: ARG002
        return {"value": 1, "label": "thing", "status": "ok"}
