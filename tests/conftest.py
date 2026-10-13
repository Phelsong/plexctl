"""Pytest configuration shared across the suite.

The ``pin`` feature persists its state (``pin.json`` and the ``last_output.json``
stash) in the user's real config directory. Left unguarded, any test that drives
a real CLI command with ``--csv`` would overwrite that shared file with test
data — polluting ``plexctl pin`` for the developer running the suite.

We therefore point ``plexctl.pin.config_dir`` at a throwaway ``tmp_path`` for
every test. We deliberately do *not* patch ``plexctl.config.config_dir``: the
config-loading tests assert on the real default path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


@pytest.fixture(autouse=True)
def isolate_pin_state(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Redirect pin's state files to an isolated temp dir for the duration of a test."""
    monkeypatch.setattr("plexctl.pin.config_dir", lambda: tmp_path)
