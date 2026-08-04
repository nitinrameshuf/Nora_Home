"""
Root conftest: the compact test reporter.

Why this exists: the suite is meant to be run on the Pi over SSH by an agent,
and pytest's normal output is long — every passing test gets a line, every
failure gets a full traceback, and reading that back costs far more tokens than
the information in it is worth.

So this replaces the summary with a fixed-size report: one line per subsystem,
then one line per failure with only its assertion. A green run is ~20 lines no
matter how many tests there are; a red run adds two lines per failure. The full
tracebacks still exist — `scripts/run-tests.sh` writes them to
`logs/test-full.txt` — so the detail is one file read away when it is actually
needed, instead of being paid for on every run.

Lives at the repo root rather than in tests/ because a root conftest is the only
one pytest guarantees to load before collection starts.
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict

BAR = "─" * 62

# Test files are named test_<subsystem>.py; the subsystem is what the report
# groups by, because "which part of the house is broken" is the first question.
_results: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
_failures: list[tuple[str, str]] = []
_started_at = time.time()


def _subsystem(nodeid: str) -> str:
    name = nodeid.split("::")[0].rsplit("/", 1)[-1]
    if name.startswith("test_"):
        name = name[5:]
    return name.removesuffix(".py")


def _one_line_reason(report) -> str:
    """The assertion, not the traceback. Pytest's longrepr ends with the actual
    error line ('E   AssertionError: ...'); that line alone is nearly always
    enough to know what broke."""
    text = str(getattr(report, "longrepr", "") or "")
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("E "):
            return stripped[1:].strip()[:160]
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()[:160]
    return "failed with no message"


def pytest_runtest_logreport(report):
    if report.when == "call":
        if report.passed:
            _results[_subsystem(report.nodeid)]["passed"] += 1
        elif report.failed:
            _results[_subsystem(report.nodeid)]["failed"] += 1
            _failures.append((report.nodeid, _one_line_reason(report)))
    elif report.when == "setup":
        if report.skipped:
            _results[_subsystem(report.nodeid)]["skipped"] += 1
        elif report.failed:
            # An error in a fixture never reaches the call phase, so it would
            # otherwise vanish from the report entirely.
            _results[_subsystem(report.nodeid)]["failed"] += 1
            _failures.append((report.nodeid, "ERROR in setup: " + _one_line_reason(report)))


def pytest_terminal_summary(terminalreporter, exitstatus, config):  # noqa: ARG001
    from django.conf import settings

    write = terminalreporter.write_line
    totals = defaultdict(int)

    write("")
    write(BAR)
    write(" NORA HOME — test report")
    try:
        engine = settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1]
        env = settings.NORA_HOME_ENV
    except Exception:  # settings may be unusable if collection itself failed
        engine, env = "?", "?"
    write(f" {time.strftime('%Y-%m-%d %H:%M:%S')} · {env} · {engine} · "
          f"python {sys.version.split()[0]}")
    write(BAR)

    for name in sorted(_results):
        counts = _results[name]
        for key, value in counts.items():
            totals[key] += value
        line = f"  {name:<22}{counts['passed']:>4} ok"
        if counts["failed"]:
            line += f"   {counts['failed']} FAIL"
        if counts["skipped"]:
            line += f"   {counts['skipped']} skip"
        write(line)

    # Collection errors never reach a test's call phase, so they are invisible to
    # the per-test hooks above. Reporting a green run when the suite did not even
    # import would be the worst possible failure for a report meant to be trusted
    # without reading the raw output.
    collect_errors = [r for r in terminalreporter.stats.get("error", [])
                      if getattr(r, "when", None) == "collect"]
    if collect_errors:
        write(BAR)
        write(" COLLECTION ERRORS — tests below did not run")
        for report in collect_errors:
            write(f"  {str(report.nodeid).split('/')[-1]}")
            write(f"    {_one_line_reason(report)}")

    if _failures:
        write(BAR)
        write(" FAILURES")
        for nodeid, reason in _failures:
            write(f"  {nodeid.split('/')[-1]}")
            write(f"    {reason}")

    write(BAR)
    if collect_errors:
        verdict = f"BROKEN · {len(collect_errors)} file(s) failed to load"
    elif totals["failed"]:
        verdict = f"{totals['failed']} FAILED"
    elif exitstatus != 0:
        # Anything else non-zero: no tests collected, an internal error, a
        # keyboard interrupt. Never claim success on it.
        verdict = f"NOT OK · pytest exit status {exitstatus}"
    else:
        verdict = "ALL PASSED"
    write(f" {verdict} · {totals['passed']} passed · {totals['failed']} failed · "
          f"{totals['skipped']} skipped · {time.time() - _started_at:.1f}s")
    write(BAR)
