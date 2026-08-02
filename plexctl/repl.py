"""Interactive REPL mode for plexctl.

Drops into a prompt where plexctl subcommands can be run without the
``plexctl`` prefix. The Typer app is loaded once and reused for every
line, so heavy imports (plexapi, httpx) only fire on the first command
that needs them.

Usage::

    plexctl repl
    plexctl> library list
    plexctl> server info
    plexctl> exit

Lines are split with :mod:`shlex` so quoted arguments work as expected.
Empty lines are skipped. ``exit``, ``quit``, and ``EOF`` (Ctrl-D) leave
the loop.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

import click
import typer
from rich.console import Console

if TYPE_CHECKING:
    from click import Command

_HISTORY_LIMIT = 100


def _enable_readline_history() -> None:
    """Enable readline-backed line editing and history (Up/Down arrows).

    Uses the stdlib ``readline`` module when available (Linux/macOS via
    GNU readline). No-op on platforms without readline (e.g. Windows
    without pyreadline3) — the REPL still works, just without history.
    """
    try:
        import readline  # noqa: F401 — import side effect enables line editing
    except ImportError:
        return


def _load_history(path: str) -> None:
    """Load readline history from ``path`` if it exists."""
    try:
        import readline

        try:
            readline.read_history_file(path)
        except FileNotFoundError:
            pass
    except ImportError:
        pass


def _save_history(path: str) -> None:
    """Persist readline history to ``path``."""
    try:
        import readline

        readline.set_history_length(_HISTORY_LIMIT)
        readline.write_history_file(path)
    except (ImportError, OSError):
        pass


_PROMPT = "plexctl> "
_BANNER = (
    "[bold cyan]plexctl REPL[/bold cyan] — type a command without the "
    "'plexctl' prefix. 'exit' or Ctrl-D to quit."
)
_FAREWELL = "[dim]bye.[/dim]"
_EXIT_WORDS = frozenset({"exit", "quit"})

console = Console()


def _make_runner(app: typer.Typer) -> Command:
    """Build a Click command once from the Typer app and reuse it."""
    from typer.main import get_command

    return get_command(app)


def _run_line(runner: Command, line: str) -> None:
    """Dispatch a single input line through the Click command tree."""
    try:
        args = shlex.split(line)
    except ValueError as exc:
        console.print(f"[red]Parse error: {exc}[/red]")
        return

    if not args:
        return

    try:
        runner.main(args, standalone_mode=False, prog_name="plexctl")
    except typer.Exit:
        # Commands raise typer.Exit(1) on controlled failures; swallow so
        # the REPL keeps running.
        pass
    except SystemExit:
        # Click raises SystemExit(0) for --help / successful commands
        # when standalone_mode is False. Ignore the exit, keep looping.
        pass
    except click.exceptions.UsageError as exc:
        console.print(f"[red]Usage error: {exc.message}[/red]")
    except click.exceptions.Abort:
        console.print("[red]Aborted.[/red]")
    except Exception as exc:
        # Surface unexpected errors without crashing the REPL.
        console.print(f"[red]Error: {exc}[/red]")


def _history_path() -> str:
    """Return the path to the REPL history file."""
    from plexctl.config import config_dir

    return str(config_dir() / "repl_history")


def repl_loop(app: typer.Typer) -> None:
    """Run the interactive REPL loop for the given Typer app."""
    runner = _make_runner(app)
    console.print(_BANNER)

    # Enable readline line editing + Up/Down history navigation
    _enable_readline_history()
    hist_path = _history_path()
    _load_history(hist_path)

    try:
        while True:
            try:
                line = input(_PROMPT)
            except EOFError:
                console.print()
                break
            except KeyboardInterrupt:
                console.print()  # newline after ^C, stay in REPL
                continue

            if line.strip().lower() in _EXIT_WORDS:
                break

            _run_line(runner, line)
    finally:
        _save_history(hist_path)

    console.print(_FAREWELL)


def register_repl(app: typer.Typer) -> None:
    """Register the ``repl`` command on the root Typer app."""

    @app.command(name="repl")
    def _repl() -> None:
        """Start an interactive REPL for running plexctl commands.

        Commands are typed without the ``plexctl`` prefix::

            plexctl repl
            plexctl> library list
            plexctl> server info
            plexctl> exit

        The Typer app is loaded once, so subsequent commands skip import
        and connection overhead.
        """
        repl_loop(app)


def register_help(app: typer.Typer) -> None:
    """Register a ``help`` command on the root Typer app.

    ``plexctl help`` shows the top-level command list; ``plexctl help <cmd>``
    shows help for a specific command or subcommand. Especially useful in
    the REPL where ``--help`` would otherwise exit the loop.
    """

    @app.command(name="help")
    def _help(
        args: list[str] = typer.Argument(  # noqa: B008
            None, help="Command path to show help for (e.g. 'library list')."
        )
    ) -> None:
        """Show help for plexctl or a specific command.

        Examples::

            plexctl help
            plexctl help library
            plexctl help library list
        """
        runner = _make_runner(app)
        full_args = [*args, "--help"] if args else ["--help"]
        try:
            runner.main(full_args, standalone_mode=False, prog_name="plexctl")
        except (typer.Exit, SystemExit):
            pass


def main() -> None:
    """Entry point for ``python -m plexctl.repl``."""
    from plexctl.cli import app

    repl_loop(app)


if __name__ == "__main__":
    main()
