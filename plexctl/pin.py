"""Pinned-table support for plexctl.

Lets a user "pin" the tabular output of one command so it is reprinted
below every subsequent command's output — a lightweight reference pane
without a full TUI.

Flow:
    1. ``plexctl movies list``          → any command run (recorded on completion)
    2. ``plexctl pin``                  → pins it (re-running with --csv if needed)
    3. ``plexctl server info``          → prints info, then the pinned table
    4. ``plexctl unpin``                → clears it

State is a set of JSON files in the config dir, so pins survive across
process invocations (each CLI call is a fresh process):

- ``pin.json`` — the currently pinned table.
- ``last_output.json`` — {source, csv} stashed by ``write_csv_to_output``
  on every stdout-CSV run (``--csv`` without ``--output``).
- ``last_command.json`` — {args} recorded after every regular command,
  so ``plexctl pin`` can re-run one that didn't pass ``--csv`` with the
  flag added and capture its CSV output in the background.

Commands that don't support ``--csv`` (mostly mutating commands) are
never replayed — ``pin`` refuses them with a clear error instead.
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import typer
from rich.console import Console
from rich.table import Table

from plexctl.config import config_dir

if TYPE_CHECKING:
    from pathlib import Path

console = Console()

_PIN_FILE = "pin.json"
_LAST_OUTPUT_FILE = "last_output.json"
_LAST_COMMAND_FILE = "last_command.json"

# Commands never recorded or replayed: they don't produce tables, and
# pinning must keep targeting the previous real command.
_META_COMMANDS = frozenset({"pin", "unpin", "repl", "help"})

# Set on the background replay child so it can't reprint an existing
# pinned table into the CSV being captured.
_NO_REPRINT_ENV = "PLEXCTL_NO_REPRINT"
_REPLAY_TIMEOUT_SECONDS = 120


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


_PIN_MAX_CELL_CHARS = 72
_MIN_COLUMN_WIDTH = 6


def _collapse_cell(value: str) -> str:
    """Flatten embedded newlines/padding to single spaces (one terminal line)."""
    return " ".join(value.split())


def _truncate_cell(value: str, limit: int = _PIN_MAX_CELL_CHARS) -> str:
    """Collapse whitespace and clip long values to one line.

    Pinned tables are a reference pane; full summaries are for the
    original command's output. Anything longer than ``limit`` characters
    is cut with a trailing ellipsis.
    """
    collapsed = _collapse_cell(value)
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: max(limit - 1, 1)].rstrip() + "…"


def _table_chrome(column_count: int) -> int:
    """Characters the table frame spends per row: padding and column dividers."""
    return 3 * column_count - 1


def _fit_column_widths(natural: list[int], available: int) -> list[int]:
    """Shrink the widest columns proportionally until the table fits.

    Keeps every column above ``_MIN_COLUMN_WIDTH``; narrow data columns
    (key/year/rating) keep their natural size while wide ones (summary,
    studio) absorb the overflow. When the terminal is too narrow to hold
    even the minimum widths, the natural widths are returned and rich
    degrades gracefully.
    """
    if sum(natural) <= available:
        return list(natural)
    minimum_total = _MIN_COLUMN_WIDTH * len(natural)
    if minimum_total > available:
        return list(natural)

    excess = [max(0, width - _MIN_COLUMN_WIDTH) for width in natural]
    total_excess = sum(excess)
    if total_excess == 0:
        return list(natural)

    keep = max(0, total_excess - (sum(natural) - available))
    scale = keep / total_excess
    widths = [
        width if cut == 0 else _MIN_COLUMN_WIDTH + round(cut * scale)
        for width, cut in zip(natural, excess, strict=True)
    ]
    while sum(widths) > available:
        widest = max(range(len(widths)), key=widths.__getitem__)
        widths[widest] -= 1
    return widths


def render_pin() -> Table | None:
    """Build the pinned rich Table, or None when nothing is pinned.

    Rows render one terminal line per record: cell text is collapsed,
    clipped with an ellipsis, and column widths are fitted to the console
    so wide summaries never fold into a wall of text.
    """
    pin = load_pin()
    if pin is None:
        return None

    headers = [str(col) for col in pin["headers"]]
    cells = [[_collapse_cell(str(row.get(col, ""))) for col in headers] for row in pin["rows"]]
    natural = [
        max([len(headers[i])] + [len(row[i]) for row in cells]) for i in range(len(headers))
    ]
    widths = _fit_column_widths(natural, max(console.width - _table_chrome(len(headers)), 1))

    table = Table(
        title=f"📌 {pin['source']}", title_justify="left", border_style="dim", show_edge=False
    )
    for header, width in zip(headers, widths, strict=True):
        table.add_column(
            header, style="cyan", overflow="ellipsis", no_wrap=True, max_width=max(width, 3)
        )
    for row in cells:
        table.add_row(
            *[_truncate_cell(cell, width) for cell, width in zip(row, widths, strict=True)]
        )
    return table


def print_pin() -> None:
    """Render the pinned table to the module console."""
    table = render_pin()
    if table is not None:
        console.print()
        console.print(table)


# --- Source labelling --------------------------------------------------------


def command_source() -> str:
    """Return a human-readable label for the command currently running.

    Prefers the live Click context so it works inside the REPL (where
    ``sys.argv`` only reflects the launcher, not the in-REPL command).
    Falls back to ``sys.argv`` for anything run outside a Click context.

    Examples::

        "plexctl library list"
        "plexctl server info"
    """
    try:
        import click

        ctx: Any = click.get_current_context()
    except (ImportError, RuntimeError):
        ctx = None

    if ctx is not None:
        names: list[str] = []
        current: Any = ctx
        while current is not None:
            command = getattr(current, "command", None)
            name = getattr(command, "name", None)
            if name:
                names.append(name)
            current = getattr(current, "parent", None)
        names.reverse()
        label = " ".join(names)
        if label:
            return label

    return " ".join(sys.argv[1:]) or "previous command"


# --- Last-command CSV stash ---------------------------------------------------


def _last_output_path() -> Path:
    """Return the path of the last-command CSV cache."""
    return config_dir() / _LAST_OUTPUT_FILE


def stash_last_output(csv_text: str, source: str) -> None:
    """Persist the last command's CSV and its label for a later ``plexctl pin``.

    Written by ``write_csv_to_output`` on every stdout-CSV run
    (``--csv`` without ``--output``), so ``plexctl pin`` — a fresh
    process — can capture it without re-hitting the server.
    """
    payload = {"source": source, "csv": csv_text}
    _last_output_path().write_text(json.dumps(payload))


def read_stash() -> tuple[str, str]:
    """Return (csv_text, source) from the CSV state cache."""
    try:
        data = json.loads(_last_output_path().read_text())
    except (OSError, json.JSONDecodeError):
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    csv_text = data.get("csv")
    if not isinstance(csv_text, str):
        csv_text = ""
    return csv_text, str(data.get("source") or "")


def reset_last_output() -> None:
    """Drop any previously stashed CSV.

    A run that did not end with stdout CSV must invalidate older stashes,
    so ``plexctl pin`` replays the last command instead of pinning stale
    data from an earlier one.
    """
    _last_output_path().write_text(json.dumps({"source": "", "csv": ""}))


def _writes_stdout_csv(args: list[str]) -> bool:
    """Whether argv tokens match write_csv_to_output's stdout-CSV path."""
    redirects_output = any(
        arg in ("--output", "-o") or arg.startswith("--output=") or arg.startswith("-o=")
        for arg in args
    )
    return "--csv" in args and not redirects_output


# --- Last-command recording ---------------------------------------------------


def _last_command_path() -> Path:
    """Return the path of the recorded last-command argv."""
    return config_dir() / _LAST_COMMAND_FILE


def record_last_command(args: list[str]) -> None:
    """Persist the argv tokens of the last regular command run."""
    payload = {"args": list(args)}
    _last_command_path().write_text(json.dumps(payload))


def load_last_command() -> list[str] | None:
    """Return the recorded argv tokens, or None when nothing is recorded."""
    try:
        data = json.loads(_last_command_path().read_text())
    except (OSError, json.JSONDecodeError):
        return None
    args = data.get("args") if isinstance(data, dict) else None
    if not isinstance(args, list) or not args:
        return None
    return [str(arg) for arg in args]


def record_command_run(args: list[str], failed: bool = False) -> None:
    """Record a completed command run for ``plexctl pin``.

    Callers run this *after* the command body so ``last_output.json`` is
    already up to date. Meta commands (pin/unpin/repl/help) are skipped:
    they don't produce tables and must not retarget the pin. When a run
    leaves no fresh stdout CSV (failed, plain-table, or redirected), any
    older stash is dropped so ``pin`` replays instead of pinning stale
    data from an earlier command.
    """
    if not args or args[0] in _META_COMMANDS or args[0].startswith("-"):
        if failed:
            reset_last_output()
        return
    record_last_command(args)
    if failed or not _writes_stdout_csv(args):
        reset_last_output()


# --- Background replay --------------------------------------------------------


def _leaf_supports_csv(app: typer.Typer, args: list[str]) -> str | None:
    """Check that the command targeted by ``args`` accepts ``--csv``.

    Returns None when the resolved leaf command supports ``--csv``;
    otherwise returns a short reason phrase (usable mid-sentence).
    """
    import click
    from typer.main import get_command

    try:
        command: Any = get_command(app)
        for token in args:
            if not isinstance(command, click.Group):
                break
            command = command.commands.get(token)
            if command is None:
                break
    except Exception:
        return "could not be resolved against the command tree"

    has_csv_flag = any(
        "--csv" in getattr(param, "opts", ()) for param in getattr(command, "params", ())
    )
    if not has_csv_flag:
        return "does not support --csv"
    return None


def _replay_args(args: list[str]) -> list[str]:
    """Return argv tokens for replaying ``args`` with ``--csv`` added.

    Drops ``--output/-o`` redirections — the replay always writes its CSV
    to stdout — and makes sure ``--csv`` is present exactly once.
    """
    replay: list[str] = []
    skip_value = False
    for token in args:
        if skip_value:
            skip_value = False
            continue
        if token in ("--output", "-o"):
            skip_value = True
            continue
        if token.startswith("--output=") or token.startswith("-o="):
            continue
        replay.append(token)
    if "--csv" not in replay:
        replay.append("--csv")
    return replay


def _replay_for_csv(app: typer.Typer, args: list[str]) -> str:
    """Re-run the last command with ``--csv`` and return its CSV output.

    Runs in a fresh subprocess so the replayed command's own output stays
    out of the user's terminal — the "background" behavior. The child sets
    PLEXCTL_NO_REPRINT so an existing pinned table can never bleed into
    the captured CSV.

    Raises ValueError with a user-facing message on any failure.
    """
    reason = _leaf_supports_csv(app, args)
    if reason is not None:
        raise ValueError(
            f"last command 'plexctl {' '.join(args)}' {reason}; "
            "retry it with --csv to pin that table"
        )

    replay = _replay_args(args)
    env = dict(os.environ)
    env[_NO_REPRINT_ENV] = "1"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "plexctl", *replay],
            capture_output=True,
            text=True,
            timeout=_REPLAY_TIMEOUT_SECONDS,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"background re-run of 'plexctl {' '.join(args)}' timed out") from exc
    except OSError as exc:
        raise ValueError(f"background re-run failed: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        tail = detail[-1] if detail else "no error output"
        raise ValueError(
            f"background re-run of 'plexctl {' '.join(args)}' failed "
            f"(exit {result.returncode}): {tail}"
        )
    if not result.stdout.strip():
        raise ValueError("background re-run produced no CSV (nothing tabular to pin)")
    return result.stdout


def pin_last_command(app: typer.Typer) -> tuple[int, str, bool]:
    """Pin the last executed command's output, replaying it when needed.

    Fast path: a ``--csv`` run wrote stdout CSV to the stash and can be
    pinned as-is. Otherwise the recorded command is re-run in the
    background with ``--csv`` and its output is captured. Meta commands
    never overwrite the record, so re-pinning keeps targeting the same
    real command.

    Returns (pinned row count, source label, replayed).
    """
    tokens = load_last_command()
    csv_text, source = read_stash()

    if tokens is None:
        # Only the legacy stash state exists; honour it.
        if not csv_text:
            raise ValueError("no previous command found (run any plexctl command first)")
        return capture_csv(csv_text, source or "previous command"), source, False

    if _writes_stdout_csv(tokens) and csv_text:
        label = source or " ".join(["plexctl", *tokens])
        return capture_csv(csv_text, label), label, False

    csv_text = _replay_for_csv(app, tokens)
    source = " ".join(["plexctl", *tokens])
    return capture_csv(csv_text, source), source, True


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
        """Pin the last command's output, reprinted after every command.

        Works whether or not the last run passed ``--csv``: a CSV run is
        pinned from its captured output, and any other command is quietly
        re-run with ``--csv`` in a background subprocess::

            plexctl movies list --csv   # CSV run: pinned instantly
            plexctl pin                 # pin the latest command
            plexctl server info         # info, then the pinned table
            plexctl unpin               # clear it
        """
        try:
            rows, source, replayed = pin_last_command(app)
        except ValueError as exc:
            console.print(f"[red]Cannot pin: {exc}[/red]")
            raise typer.Exit(code=1) from None
        note = " (re-ran with --csv in the background)" if replayed else ""
        console.print(
            f"[green]📌 Pinned {rows} row(s) from '{source}'.{note} "
            f"Reprints after every command.[/green]"
        )

    @app.command("unpin")  # type: ignore[untyped-decorator]
    def _unpin_command() -> None:
        """Clear the pinned table."""
        _unpin()

    # Hook the group-level result callback: Click invokes it after every
    # top-level command finishes. Must be set on info before the Click
    # group is built (get_command reads it at build time).
    app.info.result_callback = _reprint_pin


def _reprint_pin(*results: Any, **kwargs: Any) -> None:
    """Root result callback: record the run and reprint the pinned table.

    The ``repl`` command is a long-running session, not a one-shot
    command, so the session itself is skipped here (in-session lines
    record through ``repl._run_line`` instead). A background replay child
    sets PLEXCTL_NO_REPRINT and skips everything entirely: its prints and
    its recording must stay out of the user's terminal and history.
    """
    try:
        import click

        ctx = click.get_current_context()
    except RuntimeError:
        ctx = None
    root = ctx.find_root() if ctx is not None else None
    if getattr(root, "invoked_subcommand", None) == "repl":
        return
    if os.environ.get(_NO_REPRINT_ENV):
        return

    tokens = [str(arg) for arg in sys.argv[1:]]
    if tokens and tokens[0] in _META_COMMANDS:
        print_pin()
        return
    record_command_run(tokens)
    print_pin()
