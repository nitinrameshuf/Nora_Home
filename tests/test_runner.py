"""
The `nora` runner script.

A shell script cannot be unit-tested the way Python can, but the failure mode
that actually bites here is drift: a command in the dispatcher with no function
behind it, or a working command nobody can discover because it is missing from
`help`. Both are the same shape as the kiosk-action bug — something that looks
wired up and is not — so they are checked the same way, by reading the source.

The behaviour of each command is verified by running it, on the Pi. See
docs/Main_App/testing.md.
"""

from __future__ import annotations

import re
import stat
import subprocess
from pathlib import Path

import pytest
from django.conf import settings

RUNNER = Path(settings.BASE_DIR) / "nora"


@pytest.fixture(scope="module")
def source() -> str:
    return RUNNER.read_text()


def test_the_runner_exists_and_is_executable():
    assert RUNNER.exists(), "the nora runner is missing"
    assert RUNNER.stat().st_mode & stat.S_IXUSR, "nora is not executable (chmod +x)"


def test_the_runner_is_valid_shell():
    """A syntax error here breaks every operation on the Pi at once."""
    result = subprocess.run(["bash", "-n", str(RUNNER)], capture_output=True, text=True)

    assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"


def _dispatched_commands(source: str) -> set[str]:
    """Every name the case statement accepts, aliases included."""
    block = source[source.index('COMMAND="${1:-help}"'):]
    names: set[str] = set()
    for line in block.splitlines():
        match = re.match(r"\s{4}([a-z|_\-]+)\)\s+cmd_", line)
        if match:
            names.update(match.group(1).split("|"))
    return names


def _implemented_commands(source: str) -> set[str]:
    return set(re.findall(r"^cmd_([a-z_]+)\(\)", source, re.M))


def test_every_dispatched_command_has_a_function(source):
    """A case arm pointing at a function that does not exist fails only when
    someone reaches for that command — usually mid-incident."""
    called = set(re.findall(r"\)\s+(cmd_[a-z_]+) ", source))
    implemented = {f"cmd_{name}" for name in _implemented_commands(source)}

    missing = called - implemented

    assert not missing, f"dispatched but not implemented: {sorted(missing)}"


def test_every_command_appears_in_help(source):
    """A command nobody can discover may as well not exist. `help` is the only
    documentation of this script that is guaranteed to be in front of the person
    who needs it."""
    help_text = source[source.index("cmd_help() {"):source.index("# ── dispatch")]

    # Aliases do not each need their own line; the primary name does.
    aliases = {"start", "stop", "ps", "deploy", "--help", "-h"}
    undocumented = [
        name for name in _dispatched_commands(source) - aliases
        if not re.search(rf"^\s+{re.escape(name)}\b", help_text, re.M)
    ]

    assert not undocumented, f"missing from help: {sorted(undocumented)}"


def test_help_mentions_the_recreate_trap(source):
    """The single most confusing thing about this stack: editing .env and
    restarting does nothing, because a container keeps the environment it
    started with. It cost a session. Help has to say so."""
    help_text = source[source.index("cmd_help() {"):source.index("# ── dispatch")]

    assert "recreate" in help_text
    assert re.search(r"\.env", help_text), "help does not explain what recreate is for"


@pytest.mark.parametrize("command", ["uninstall", "restore"])
def test_destructive_commands_confirm_first(source, command):
    """Neither should be able to destroy data because someone typed fast."""
    body = source[source.index(f"cmd_{command}() {{"):]
    body = body[:body.index("\n}\n")]

    assert "confirm " in body, f"cmd_{command} does not ask before acting"


def test_uninstall_backs_up_before_removing(source):
    body = source[source.index("cmd_uninstall() {"):]
    body = body[:body.index("\n}\n")]

    assert "cmd_backup" in body, "uninstall does not take a backup first"
    assert body.index("cmd_backup") < body.index("down --volumes"), (
        "uninstall removes the volumes before backing them up")


def test_app_uninstall_backs_up_first(source):
    body = source[source.index("cmd_app() {"):]
    body = body[:body.index("\n}\n")]

    assert "cmd_backup" in body, "uninstalling a house app takes no backup"


def test_the_runner_points_at_the_real_provisioning_script():
    """`nora install` replaced scripts/install-pi.sh as the entry point; the
    provisioning itself still has to be there."""
    provision = Path(settings.BASE_DIR) / "scripts" / "lib" / "provision-pi.sh"

    assert provision.exists(), "the provisioning script is missing"
    assert "provision-pi.sh" in RUNNER.read_text()


# Ways a document can tell someone to *run* the old script, as opposed to
# merely naming it while explaining that it moved. Only the former is a bug.
_RUNNABLE_OLD_PATHS = re.compile(
    r"(?:\./|sudo\s+|bash\s+|main/)scripts/(?:pre-)?install-pi\.sh")


def test_nothing_still_tells_you_to_run_the_old_install_script():
    """Renaming a script and leaving the docs pointing at the old path is how a
    fresh Pi gets set up wrongly. Mentioning the old name while explaining the
    move is fine — this looks for instructions, not for the string."""
    base = Path(settings.BASE_DIR)
    offenders = []

    for path in list(base.glob("*.md")) + list((base / "docs").rglob("*")) + \
            list((base / "scripts").rglob("*")) + [base / "Makefile", base / "nora"]:
        if not path.is_file() or path.suffix not in {".md", ".html", ".sh", ""}:
            continue
        if path.name == "progress.md":
            continue  # the log is history; it should still say what happened
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _RUNNABLE_OLD_PATHS.search(text):
            offenders.append(str(path.relative_to(base)))

    assert not offenders, f"still telling people to run the old script: {offenders}"


def test_help_runs_and_exits_cleanly():
    result = subprocess.run([str(RUNNER), "help"], capture_output=True, text=True,
                            cwd=settings.BASE_DIR)

    assert result.returncode == 0
    assert "nora — the one command" in result.stdout


def test_an_unknown_command_fails_loudly():
    result = subprocess.run([str(RUNNER), "definitely-not-a-command"],
                            capture_output=True, text=True, cwd=settings.BASE_DIR)

    assert result.returncode != 0
    assert "unknown command" in result.stderr
