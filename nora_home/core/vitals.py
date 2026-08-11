"""
The Pi's vitals, as the rail shows them.

One list of {key, value, bar, warm} — a short mono label, a formatted value, and
optionally a 0-100 bar. The rail renders whatever it is given, so adding a vital
is adding an entry here and nothing else.

The design mockup's rail showed six vitals — CPU, MEM, TEMP, FAN, LOAD, UP — and
Story 52 is what makes the last four real, as *telemetry series* recorded every
five minutes by nora_home.telemetry.tasks.collect_vitals, rather than read from
/proc on every page render. TEMP and DISK stay probed directly below (they were
already cheap and already this file's own read); the rest come from
telemetry.api.latest_value(), one indexed query per vital. **Still only what is
genuinely measured appears** — a vital with no reading yet (a fresh install,
before the first five-minute tick) is simply absent from the list rather than
shown as zero, because a zero would be believed.

Cheap reads only, and that constraint is load-bearing. This runs in a context
processor on every page in the house. check_disk()/check_cpu_temperature() are
local file reads; latest_value() is one indexed row lookup each. None of it is
collect_health(), which opens TCP connections to redis, rabbitmq, mongo and
MinIO with a 2s timeout each — eight seconds of socket work per page render is
the kind of thing that looks fine on a laptop and makes the wall feel broken.
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
CPU_WARM_PERCENT = 85.0
MEMORY_WARM_PERCENT = 85.0
LOAD_CEILING = 8.0   # 2x a 4-core Pi 5; matches collect_vitals()'s own warn_above
LOAD_WARM = 4.0


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

    from nora_home.telemetry.api import latest_value

    try:
        cpu = latest_value("pi.cpu_percent")
        if cpu is not None:
            vitals.append({
                "key": "CPU",
                "value": f"{cpu:.0f}%",
                "bar": _scale(cpu, 0, 100),
                "warm": cpu >= CPU_WARM_PERCENT,
            })
    except Exception:
        logger.exception("The cpu vital could not be read")

    try:
        memory = latest_value("pi.memory_percent")
        if memory is not None:
            vitals.append({
                "key": "MEM",
                "value": f"{memory:.0f}%",
                "bar": _scale(memory, 0, 100),
                "warm": memory >= MEMORY_WARM_PERCENT,
            })
    except Exception:
        logger.exception("The memory vital could not be read")

    try:
        fan = latest_value("pi.fan_rpm")
        if fan is not None:
            vitals.append({"key": "FAN", "value": f"{fan:.0f}", "warm": False})
    except Exception:
        logger.exception("The fan vital could not be read")

    try:
        load = latest_value("pi.load_average")
        if load is not None:
            vitals.append({
                "key": "LOAD",
                "value": f"{load:.1f}",
                "bar": _scale(load, 0, LOAD_CEILING),
                "warm": load >= LOAD_WARM,
            })
    except Exception:
        logger.exception("The load vital could not be read")

    try:
        uptime = latest_value("pi.uptime_hours")
        if uptime is not None:
            value = f"{uptime / 24:.0f}d" if uptime >= 48 else f"{uptime:.0f}h"
            vitals.append({"key": "UP", "value": value, "warm": False})
    except Exception:
        logger.exception("The uptime vital could not be read")

    return vitals
