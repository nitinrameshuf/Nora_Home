"""
The Pi's vitals, as the rail shows them.

One list of {key, value, bar, warm} — a short mono label, a formatted value, and
optionally a 0-100 bar. The rail renders whatever it is given, so adding a vital
is adding an entry here and nothing else.

**Only what is genuinely measured appears.** The design mockup's rail showed six
vitals — CPU, MEM, TEMP, FAN, LOAD, UP — and its own comment admits only
temperature and disk are collected today. Story 52 adds the rest as *telemetry
series* (with history, rollups and thresholds), which is a different and better
thing than reading /proc on every page render. Until it lands this shows the two
that are real. A rail that showed a plausible CPU number would be worse than a
short rail: it would be believed.

Cheap probes only, and that constraint is load-bearing. This runs in a context
processor on every page in the house, so it calls check_disk() and
check_cpu_temperature() directly — both are local file reads — and never
collect_health(), which additionally opens TCP connections to redis, rabbitmq,
mongo and MinIO with a 2s timeout each. Eight seconds of socket work per page
render is the kind of thing that looks fine on a laptop and makes the wall feel
broken.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# The Pi 5 throttles at 80°C and its idle is ~45°C, so a 0-85 bar spends its
# whole life in the top half and says nothing. 30-85 is the range worth seeing.
TEMP_FLOOR_C = 30.0
TEMP_CEILING_C = 85.0
TEMP_WARM_C = 70.0   # matches check_cpu_temperature()'s own "warning" threshold
DISK_WARM_PERCENT = 80.0


def _scale(value: float, low: float, high: float) -> int:
    return max(0, min(100, round((value - low) / (high - low) * 100)))


def rail_vitals() -> list[dict]:
    """Vitals for the rail, newest reading each. Never raises: this is chrome on
    every page, and a failed probe should cost that vital, not the page."""
    from nora_home.core.health import check_cpu_temperature, check_disk

    vitals: list[dict] = []

    try:
        temp = check_cpu_temperature()
        celsius = temp.get("celsius")
        if celsius is not None:
            vitals.append({
                "key": "TEMP",
                "value": f"{celsius:.0f}°",
                "bar": _scale(celsius, TEMP_FLOOR_C, TEMP_CEILING_C),
                "warm": celsius >= TEMP_WARM_C,
            })
    except Exception:
        logger.exception("The temperature vital could not be read")

    try:
        disk = check_disk()
        percent = disk.get("percent_used")
        if percent is not None:
            vitals.append({
                "key": "DISK",
                "value": f"{percent:.0f}%",
                "bar": _scale(percent, 0, 100),
                "warm": percent >= DISK_WARM_PERCENT,
            })
    except Exception:
        logger.exception("The disk vital could not be read")

    return vitals
