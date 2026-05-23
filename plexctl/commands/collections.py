"""Collection management commands for plexctl.

These commands are accessible via `plexctl library collections`.
A deprecated top-level alias `plexctl collections` also exists for
backward compatibility.
"""

import typer
from rich.console import Console
from rich.table import Table

from plexctl.client import PlexClient
from plexctl.config import load_config
from plexctl.converters import collection_info_to_csv, collection_metadata_to_csv
from plexctl.csv_utils import write_csv_to_output
from plexctl.options import CsvFlag, OutputFile
from plexctl.services.library import LibraryService

collections_app = typer.Typer(
    name="collections", help="Manage Plex collections.", no_args_is_help=True
)
console = Console()


def _get_service() -> LibraryService:
    """Load config and create a connected LibraryService."""
    config = load_config()
    client = PlexClient(config)
    return LibraryService(client)


# --- List collections --------------------------------------------------------


@collections_app.command("list")
def list_collections(
    section: str | None = typer.Option(
        None, "--section", "-s", help="Section key to filter collections"
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List all collections, optionally filtered by section."""
    service = _get_service()

    section_key = int(section) if section else None
    colls = service.list_collections(section_key=section_key)

    if not colls:
        label = f" in section {section}" if section else ""
        console.print(f"[dim]No collections found{label}.[/dim]")
        return

    if csv_output:
        rows = [collection_info_to_csv(c) for c in colls]
        write_csv_to_output(rows, output)
        return

    table = Table(title="Collections")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Smart", style="yellow")
    table.add_column("Items", style="magenta", justify="right")

    for coll in colls:
        table.add_row(coll.key, coll.title, "✓" if coll.smart else "✗", str(coll.content_count))

    console.print(table)


# --- Get collection ----------------------------------------------------------


@collections_app.command("get")
def get_collection(
    key: str = typer.Argument(help="Collection rating key"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Get detailed metadata for a collection."""
    service = _get_service()
    coll = service.get_collection(key)

    if coll is None:
        console.print(f"[red]Collection not found: {key}[/red]")
        raise typer.Exit(code=1)

    if csv_output:
        rows = [collection_metadata_to_csv(coll)]
        write_csv_to_output(rows, output)
        return

    console.print(f"\n[bold]{coll.title}[/bold]")
    console.print(f"  Key:           {coll.key}")
    console.print(f"  Smart:         {'Yes' if coll.smart else 'No'}")
    console.print(f"  Item Count:    {coll.content_count}")
    if coll.section_title:
        console.print(f"  Section:       {coll.section_title}")
    if coll.summary:
        console.print(f"\n  {coll.summary}\n")


# --- Create collection -------------------------------------------------------


@collections_app.command("create")
def create_collection(
    name: str = typer.Argument(help="Collection title"),
    section: str = typer.Option(
        ..., "--section", "-s", help="Section key to create the collection in"
    ),
    smart: bool = typer.Option(False, "--smart", help="Create a smart collection"),
) -> None:
    """Create a new collection in a library section.

    Example:
        plexctl library collections create "My Favorites" --section 2
        plexctl library collections create "Action Movies" --section 2 --smart
    """
    service = _get_service()
    coll = service.create_collection(title=name, section_key=section, smart=smart)
    console.print(f"[green]✓ Created collection '{coll.title}' (key={coll.key})[/green]")


# --- Update collection -------------------------------------------------------


@collections_app.command("update")
def update_collection(
    key: str = typer.Argument(help="Collection rating key"),
    title: str | None = typer.Option(None, "--title", "-t", help="New title for the collection"),
    summary: str | None = typer.Option(None, "--summary", help="New summary/description"),
) -> None:
    """Update a collection's metadata.

    Example:
        plexctl library collections update 12345 --title "New Name"
        plexctl library collections update 12345 --summary "Updated description"
    """
    if title is None and summary is None:
        console.print("[yellow]Specify at least --title or --summary to update.[/yellow]")
        raise typer.Exit(code=1)

    service = _get_service()
    result = service.update_collection(key, title=title, summary=summary)

    if result is None:
        console.print(f"[red]Failed to update collection {key}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]✓ Updated collection '{result.title}'[/green]")


# --- Delete collection -------------------------------------------------------


@collections_app.command("delete")
def delete_collection(
    key: str = typer.Argument(help="Collection rating key"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a collection permanently.

    The collection's member items are not deleted.

    Example:
        plexctl library collections delete 12345 --yes
    """
    if not confirm:
        console.print(f"[yellow]Will delete collection {key}. Use --yes to confirm.[/yellow]")
        raise typer.Exit(code=1)

    service = _get_service()
    service.delete_collection(key)
    console.print(f"[green]✓ Deleted collection {key}[/green]")


# --- Add items to collection --------------------------------------------------


@collections_app.command("add")
def add_to_collection(
    key: str = typer.Argument(help="Rating key of the collection"),
    items: list[str] = typer.Argument(..., help="Rating keys of items to add"),  # noqa: B008
) -> None:
    """Add items to a collection.

    Example:
        plexctl library collections add 12345 56789 56790
    """
    if not items:
        console.print("[yellow]No items specified.[/yellow]")
        raise typer.Exit(code=1)

    service = _get_service()
    try:
        result = service.add_to_collection(key, items)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    if result is None:
        console.print(f"[red]Collection not found: {key}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]✓ Added {len(items)} item(s) to "
        f"'{result.title}' (now {result.content_count} items)[/green]"
    )


# --- Remove items from collection ---------------------------------------------


@collections_app.command("remove")
def remove_from_collection(
    key: str = typer.Argument(help="Rating key of the collection"),
    items: list[str] = typer.Argument(..., help="Rating keys of items to remove"),  # noqa: B008
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Remove items from a collection.

    Example:
        plexctl library collections remove 12345 56789 --yes
    """
    if not confirm:
        console.print(
            f"[yellow]Will remove {len(items)} item(s) from "
            f"collection {key}. Use --yes to confirm.[/yellow]"
        )
        raise typer.Exit(code=1)

    service = _get_service()
    try:
        service.remove_from_collection(key, items)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"[green]✓ Removed {len(items)} item(s) from collection {key}[/green]")
