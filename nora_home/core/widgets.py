"""Platform widgets — the state of the machine the house runs on."""

from __future__ import annotations

from django.utils import timezone

from nora_home.core.health import collect_health
from nora_home.core.models import SystemHealthSnapshot
from nora_home.dashboard.widgets import ChartWidget, StatWidget


class HouseHealthWidget(StatWidget):
    title = "House health"
    description = "Whether the Pi and everything it depends on is behaving."
    icon = "heart"
    sizes = ("S", "M")
    refresh_seconds = 120

    def stat(self, request):  # noqa: ARG002
        report = collect_health()
        degraded = report["degraded"]
        return {
            "value": "OK" if report["healthy"] else "Degraded",
            "label": (", ".join(degraded) if degraded else "all services up"),
            "status": "ok" if report["healthy"] else "alert",
        }


class CpuTemperatureWidget(ChartWidget):
    title = "Pi temperature"
    subtitle = "Last 24 hours"
    description = "CPU temperature. Worth watching if the Pi lives in a cupboard."
    icon = "thermometer"
    sizes = ("M", "L", "XL")
    refresh_seconds = 600

    def option(self, request):  # noqa: ARG002
        since = timezone.now() - timezone.timedelta(hours=24)
        snapshots = (SystemHealthSnapshot.objects
                     .filter(created_at__gte=since, cpu_temp_c__isnull=False)
                     .order_by("created_at")
                     .values_list("created_at", "cpu_temp_c"))

        return {
            "xAxis": {"type": "category",
                      "data": [timezone.localtime(t).strftime("%H:%M")
                               for t, _ in snapshots]},
            "yAxis": {"type": "value", "name": "°C",
                      # The Pi throttles at 80. Anchoring the axis there stops a
                      # two-degree wobble from looking like a crisis.
                      "max": 85, "min": 30},
            "series": [{
                "type": "line", "smooth": True, "showSymbol": False,
                "data": [round(temp, 1) for _, temp in snapshots],
                "markLine": {"silent": True,
                             "data": [{"yAxis": 80, "name": "throttle"}]},
            }],
        }


class DiskWidget(StatWidget):
    title = "Disk"
    description = "How much room is left on the Pi. Backups fill cards quietly."
    icon = "disk"
    sizes = ("S", "M")
    refresh_seconds = 900

    def stat(self, request):  # noqa: ARG002
        disk = collect_health()["services"].get("disk", {})
        percent = disk.get("percent_used")
        if percent is None:
            return {"value": "—", "label": "unavailable", "status": "warn"}
        return {
            "value": round(percent),
            "unit": "%",
            "label": f"{disk.get('free_gb', '?')} GB free",
            "status": "ok" if percent < 80 else ("warn" if percent < 90 else "alert"),
        }
