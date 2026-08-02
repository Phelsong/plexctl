"""Shared helpers for command modules.

These helpers consolidate repetitive presentation patterns found across
the command layer (movies, shows, music, photos, library, collections,
playlists, server, item, triage, shoko). They are intentionally thin
wrappers over Rich/Typer so the call sites stay readable while the
exact user-facing strings stay in one place.

Internal module: do not import from ``plexctl.commands.__init__``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import typer
from rich.console import Console
from rich.table import Table

from plexctl.csv_utils import from_csv, get_model_class, list_model_names, write_csv_to_output

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pydantic import BaseModel

    from plexctl.services.tree import TreeService

console = Console()


# --- Types ------------------------------------------------------------------


@runtime_checkable
class _Result(Protocol):
    """A service result with success/error status used by print_result."""

    success: bool
    error: str | None


@runtime_checkable
class _BatchResult(Protocol):
    """A batch result with totals and per-item failure details."""

    total: int
    succeeded: int
    failed: int
    results: list[Any]


# -------------------------------------------------------------


def output_csv(
    rows: Sequence[Any],
    converter: Callable[[Any], BaseModel],
    csv_output: bool,
    output: str | None,
) -> bool:
    """Write rows as CSV if csv_output is True.

    Returns True when the caller should return (the CSV was handled).
    Returns False when csv_output is False and the caller should keep
    rendering tables.
    """
    if not csv_output:
        return False
    write_csv_to_output([converter(r) for r in rows], output)
    return True


# ----------------------------------------------------


def require_section_key(tree_service: TreeService, section: str) -> str:
    """Return validated section key or print error and exit.

    Mirrors the inline block previously duplicated across movies.py,
    shows.py, music.py and photos.py: resolve the section, and on
    failure print the two-line red+dim hint and raise typer.Exit(1).
    """
    section_key = tree_service.resolve_section_key(section)
    if section_key is None:
        console.print(f"[red]Section not found: {section}[/red]")
        console.print("[dim]Use 'plexctl library list' to see available sections.[/dim]")
        raise typer.Exit(code=1)
    return section_key


# -------------------------------------------------------------


def require_confirm(confirm: bool, what: str) -> None:
    """If confirm is False, print a yellow message about `what` and exit.

    ``what`` is interpolated into the message as ``Will {what}. Use --yes
    to confirm.`` so call sites can preserve their exact wording, e.g.
    ``require_confirm(confirm, f"delete item {key}")``.
    """
    if not confirm:
        console.print(f"[yellow]Will {what}. Use --yes to confirm.[/yellow]")
        raise typer.Exit(code=1)


# ------------------------------------------------------------


def print_result(result: _Result, success_msg: str, failure_msg: str) -> None:
    """Print green success_msg if result.success, else red failure_msg with error.

    The success branch prints ``[green]✓ {success_msg}[/green]``; the
    failure branch prints ``[red]✗ {failure_msg}: {result.error}[/red]``.
    Callers embed the leading mark in their own wording to preserve the
    exact user-facing strings used previously.
    """
    if result.success:
        console.print(f"[green]✓ {success_msg}[/green]")
    else:
        console.print(f"[red]✗ {failure_msg}: {result.error}[/red]")


# ---------------------------------------------------------


def if_empty_print(rows: Sequence[Any], message: str) -> bool:
    """If rows is empty, print dim message and return True (caller returns)."""
    if not rows:
        console.print(f"[dim]{message}[/dim]")
        return True
    return False


# -----------------------------------------------------


def print_batch_result(result: _BatchResult, title: str | None = None) -> None:
    """Print batch operation summary with totals and failures list.

    Mirrors the block duplicated across triage.py's analyze/refresh
    commands: a leading optional bold title, three indented count lines
    (targeted/succeeded/failed), and a 'Failures:' list of per-item
    red marks when ``result.results`` is non-empty.
    """
    if title is not None:
        console.print(f"\n[bold]{title}[/bold]")
    console.print(f"\n  Shows targeted: {result.total}")
    console.print(f"  Succeeded:       [green]{result.succeeded}[/green]")
    console.print(f"  Failed:          [red]{result.failed}[/red]")
    if result.results:
        console.print("\n[bold]Failures:[/bold]")
        for r in result.results:
            console.print(f"  [red]✗[/red] {r.title or r.key}: {r.error}")


# ----------------------------------------------------


def media_results_table(
    title: str,
    items: Sequence[Any],
    *,
    extra_header: str | None = None,
    extra_accessor: Callable[[Any], str] | None = None,
    limit: int | None = None,
) -> Table:
    """Build the standard Key/Title/Type/Year[+extra] media results table.

    Columns follow the long-standing layout shared by item.py search,
    actor, director, genre, title and tmdb commands plus the movies and
    shows list commands:

      - Key      (cyan, right-justified)
      - Title    (green)
      - Type     (yellow)
      - Year     (magenta, right-justified)
      - optional extra column appended last

    The function only builds and returns the table — the caller prints
    it. Callers also own the trailer (``Showing N of M`` / ``Found N
    results``) so they can keep their own wording intact.
    """
    table = Table(title=title)
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Year", style="magenta", justify="right")
    if extra_header is not None and extra_accessor is not None:
        table.add_column(extra_header, style="blue")

    visible = items[:limit] if limit is not None else items
    for item in visible:
        row: list[str] = [
            item.key,
            item.title or "Unknown",
            item.media_type.value if item.media_type else "-",
            str(item.year) if item.year else "-",
        ]
        if extra_header is not None and extra_accessor is not None:
            row.append(extra_accessor(item))
        table.add_row(*row)
    return table


# -------------------------------------------------------------


def run_ingest(model: str, file: str | None, *, command_name: str) -> None:
    """Run the ingest command: validate model name, read file, parse CSV.

    Shared body for ``plexctl item ingest`` and ``plexctl triage ingest``.
    ``command_name`` is used only in error messages so the user sees which
    command they invoked. Preserves the exact output of the previously
    duplicated implementations.
    """
    if model == "list":
        names = list_model_names()
        console.print("[bold]Available model names for ingest:[/bold]")
        for name in names:
            model_class = get_model_class(name)
            field_count = len(model_class.model_fields) if model_class else 0
            console.print(f"  {name} ({field_count} fields)")
        return

    if file is None:
        console.print("[red]FILE argument is required when MODEL is not 'list'.[/red]")
        raise typer.Exit(code=1)

    model_class = get_model_class(model)
    if model_class is None:
        available = ", ".join(list_model_names())
        console.print(f"[red]Unknown model: {model}[/red]")
        console.print(f"[dim]Available models: {available}[/dim]")
        raise typer.Exit(code=1)

    csv_path = Path(file)
    if not csv_path.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(code=1)

    try:
        models = from_csv(model_class, csv_path)
    except Exception as exc:
        console.print(f"[red]Error parsing CSV: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]✓ Loaded {len(models)} {model} records from {file}[/green]")

    # Show a summary table of the ingested data
    table = Table(title=f"Ingested {model} ({len(models)} rows)")
    # Use the model's field names as columns, limited to first 6 for readability
    fields = list(model_class.model_fields.keys())
    display_fields = fields[:6]

    for field in display_fields:
        table.add_column(field, style="cyan")

    for row in models[:25]:
        values = [str(getattr(row, f, ""))[:40] for f in display_fields]
        table.add_row(*values)

    console.print(table)
    if len(models) > 25:
        console.print(f"[dim]Showing 25 of {len(models)} rows.[/dim]")
