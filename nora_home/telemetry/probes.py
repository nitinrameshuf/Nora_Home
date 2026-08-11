"""
Reading the Pi's own vitals — CPU, memory, load, uptime, fan, throttling.

Temperature and disk already exist (`nora_home.core.health`); this fills in
the rest, as telemetry series rather than folded into health.py, because
these want history and thresholds, not a pass/fail probe on a status page.

Every reader is a local file under /proc or /sys and returns `None` rather
than raising when the file is missing (a dev laptop has no fan1_input) —
`collect_vitals()` in tasks.py records whatever came back and skips the
rest, so a non-Pi machine just records fewer series.

`read_throttled()` is the one exception that shells out. `vcgencmd
get_throttled` has no /proc or /sys equivalent, and it is the most valuable
reading here: under-voltage degrades a Pi silently — dropped USB devices,
random reboots, corrupted SD writes — long before anything else reports a
problem, and every other vital in this file can look perfectly healthy while
it happens.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _cpu_times() -> tuple[float, float]:
    fields = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
    parts = [float(x) for x in fields]
    idle = parts[3] + parts[4]  # idle + iowait
    return idle, sum(parts)


def read_cpu_percent(interval: float = 0.2) -> float | None:
    """% of CPU time not idle, sampled over `interval` seconds like `top` does —
    a single /proc/stat read is a running total since boot, not a rate."""
    try:
        idle1, total1 = _cpu_times()
        time.sleep(interval)
        idle2, total2 = _cpu_times()
    except (OSError, IndexError, ValueError):
        return None
    dt = total2 - total1
    if dt <= 0:
        return None
    return round((1 - (idle2 - idle1) / dt) * 100, 1)


def read_memory_percent() -> float | None:
    try:
        text = Path("/proc/meminfo").read_text()
    except OSError:
        return None
    values = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        try:
            values[key] = float(rest.strip().split()[0])
        except (ValueError, IndexError):
            continue
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return None
    return round((1 - available / total) * 100, 1)


def read_load_average() -> float | None:
    try:
        return float(Path("/proc/loadavg").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def read_uptime_hours() -> float | None:
    try:
        seconds = float(Path("/proc/uptime").read_text().split()[0])
        return round(seconds / 3600, 1)
    except (OSError, ValueError, IndexError):
        return None


def read_fan_rpm() -> float | None:
    """The Pi 5 active cooler's tacho, wherever hwmon numbered it this boot."""
    try:
        candidates = sorted(Path("/sys/class/hwmon").glob("hwmon*/fan1_input"))
    except OSError:
        return None
    for path in candidates:
        try:
            return float(path.read_text().strip())
        except (OSError, ValueError):
            continue
    return None


def read_throttled() -> int | None:
    """The raw bitmask from `vcgencmd get_throttled`. Bit 0 is under-voltage
    happening right now; bit 16 is under-voltage having happened since boot.
    Recorded as-is — classification (any bit set is worth an alert) lives in
    the series' own alert_above, not here."""
    try:
        result = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True,
                                text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = result.stdout.strip()
    if not text.startswith("throttled=0x"):
        return None
    try:
        return int(text.split("=0x", 1)[1], 16)
    except ValueError:
        return None
