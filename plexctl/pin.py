"""Pinned-table support for plexctl.

Lets a user "pin" the tabular output of one command so it is reprinted
below every subsequent command's output — a lightweight reference pane
without a full TUI.

Flow:
    1. ``plexctl library list --csv``   → produces CSV on stdout
    2. ``plexctl pin``                  → pins that output
    3. ``plexctl server info``          → prints info, then the pinned table
    4. ``plexctl unpin``                → clears it

State is a single JSON file in the config dir, so pins survive across
process invocations (each CLI call is a fresh process).

The previous command's CSV is persisted to ``last_output.json`` by
``write_csv_to_output`` (every ``--csv`` command flows through it), so
``plexctl pin`` — a fresh process — can capture it.
"""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

import typer
from rich.console import Console
from rich.table import Table

from plexctl.config import config_dir

if TYPE_CHECKING:
    from pathlib import Path

console = Console()

_PIN_FILE = "pin.json"


# --- Pin state ---------------------------------------------------------------


def _pin_path() -> Path:
    """Return the path of the pin state file."""
    return config_dir() / _PIN_FILE


def save_pin(headers: list[str], rows: list[dict[str, str]], source: str) -> None:
    """Persist a pinned table to the config dir."""
    payload = {"headers": headers, "rows": rows, "source": source}
    _pin_path().write_text(json.dumps(payload))


def load_pin() -> dict[str, Any] | None:
    """Return the pinned table, or None when nothing is pinned."""
    try:
        data = json.loads(_pin_path().read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or "headers" not in data or "rows" not in data:
        return None
    return data


def clear_pin() -> bool:
    """Delete the pin file. Returns True if a pin existed."""
    try:
        _pin_path().unlink()
        return True
    except FileNotFoundError:
        return False


def capture_csv(csv_text: str, source: str) -> int:
    """Parse CSV text and store it as the pinned table.

    Returns the number of rows pinned.
    Raises ValueError on empty/invalid CSV so the caller can report it.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("no tabular output to pin (run a list command with --csv)")
    rows = list(reader)
    if not rows:
        raise ValueError("command produced no rows to pin")
    save_pin(list(reader.fieldnames), rows, source)
    return len(rows)


def render_pin() -> Table | None:
    """Build the pinned rich Table, or None when nothing is pinned."""
    pin = load_pin()
    if pin is None:
        return None
    table = Table(
        title=f"📌 {pin['source']}",
        title_justify="left",
        border_style="dim",
        show_edge=False,
    )
    for col in pin["headers"]:
        table.add_column(col, style="cyan", overflow="fold")
    for row in pin["rows"]:
        table.add_row(*[str(row.get(col, "")) for col in pin["headers"]])
    return table


def print_pin() -> None:
    """Render the pinned table to the module console."""
    table = render_pin()
    if table is not None:
        console.print()
        console.print(table)


# --- Last-command output capture ---------------------------------------------

_LAST_OUTPUT_FILE = "last_output.json"


def _last_output_path() -> Path:
    """Return the path of the last-command CSV cache."""
    return config_dir() / _LAST_OUTPUT_FILE


def stash_last_output(text: str, args: list[str]) -> None:
    """Persist the last command's CSV for a later ``plexctl pin``.

    Written to disk (not just memory) because each CLI invocation is a
    separate process; ``plexctl pin`` runs in a fresh interpreter.
    """
    payload = {"args": list(args), "csv": text}
    _last_output_path().write_text(json.dumps(payload))


def pin_from_last_output() -> int:
    """Pin the previous command's CSV output. Returns row count.

    Raises ValueError when there is nothing pinnable.
    """
    try:
        data = json.loads(_last_output_path().read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            "no previous CSV output found (run a list command with --csv first)"
        ) from exc
    csv_text = data.get("csv") if isinstance(data, dict) else None
    if not csv_text:
        raise ValueError("no previous CSV output found (run a list command with --csv first)")
    source = " ".join(data.get("args", [])) or "previous command"
    return capture_csv(csv_text, source)


# --- Commands ----------------------------------------------------------------


def _unpin() -> None:
    if clear_pin():
        console.print("[green]Pin cleared.[/green]")
    else:
        console.print("[yellow]Nothing pinned.[/yellow]")


# --- Root-app wiring ---------------------------------------------------------


def register_pin(app: typer.Typer) -> None:
    """Register ``pin``/``unpin`` commands plus the reprint callback.

    The reprint hooks the underlying Click group's ``result_callback``,
    which Click invokes with each command's return value *after* the
    command finishes printing — exactly where the pinned table belongs.
    """

    @app.command("pin")  # type: ignore[untyped-decorator]
    def _pin_command() -> None:
        """Pin the previous command's CSV output.

        Reprints below every subsequent command until unpinned::

            plexctl library list --csv   # produce tabular output
            plexctl pin                  # pin it
            plexctl server info          # info, then the pinned table
        """
        try:
            rows = pin_from_last_output()
        except ValueError as exc:
            console.print(f"[red]Cannot pin: {exc}[/red]")
            raise typer.Exit(code=1) from None
        console.print(
            f"[green]📌 Pinned {rows} row(s). Reprints after every command.[/green]"
        )
        print_pin()

    @app.command("unpin")  # type: ignore[untyped-decorator]
    def _unpin_command() -> None:
        """Clear the pinned table."""
        _unpin()

    # Hook the group-level result callback: Click invokes it after every
    # top-level command finishes. Must be set on info before the Click
    # group is built (get_command reads it at build time).
    app.info.result_callback = _reprint_pin


def _reprint_pin(*results: Any, **kwargs: Any) -> None:
    """Click result callback: reprint the pinned table after a command."""
    print_pin()
