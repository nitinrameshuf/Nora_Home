"""Generated documentation must match the code it was generated from.

`manage.py sync_docs` rewrites the blocks between `sync_docs` markers straight
from the registry and the published api modules. This runs `--check`, so a doc
that has drifted is a failing test rather than something noticed months later.

That distinction is the whole point. `cross-functionality.md` used to instruct
whoever changed a published function to "change its row here in the same
commit" — and `register_trackable()` still sat in five documents weeks after
the app publishing it was deleted, because nothing ever executed the promise.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command


def test_generated_docs_match_the_code():
    """Fails when a generated block is out of date. Fix by running:

        manage.py sync_docs
    """
    try:
        call_command("sync_docs", "--check")
    except SystemExit as exit_code:
        if exit_code.code == 2:
            pytest.fail("sync_docs could not find a file or its markers — see stderr")
        pytest.fail(
            "Generated documentation is out of date. Run: manage.py sync_docs")


def test_generating_twice_produces_the_same_bytes(tmp_path, settings):
    """The generator must be deterministic, or --check is permanently red for
    no reason. It was: repr() of a property embeds its memory address, so the
    app-contract table differed on every run until properties were excluded.
    """
    from nora_home.core.management.commands.sync_docs import BLOCKS

    for name, (_relative, build) in BLOCKS.items():
        assert build() == build(), f"{name} is not deterministic"
