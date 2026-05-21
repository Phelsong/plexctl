"""Library administration commands for plexctl.

Provides commands for managing library sections and collections:
- Create, list, get, and delete sections
- List section filesystem locations
- Manage collections (list, get, create, update, delete) via the 'collections' sub-group
"""

import typer
from rich.console import Console
from rich.table import Table

from plexctl.client import PlexClient
from plexctl.commands.collections import collections_app
from plexctl.commands.playlists import playlists_app
from plexctl.config import load_config
from plexctl.converters import (
    library_location_to_csv,
    library_section_to_csv,
)
from plexctl.csv_utils import write_csv_to_output
from plexctl.options import CsvFlag, OutputFile
from plexctl.services.library import LibraryService

library_app = typer.Typer(
    name="library",
    help="Manage Plex library sections and collections.",
    no_args_is_help=True,
)
console = Console()


def _get_service() -> LibraryService:
    """Load config and create a connected LibraryService."""
    config = load_config()
    client = PlexClient(config)
    return LibraryService(client)


# --- List sections -----------------------------------------------------------


@library_app.command("list")
def list_sections(
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List all library sections on the server."""
    service = _get_service()
    sections = service.list_sections()

    if not sections:
        console.print("[dim]No library sections found.[/dim]")
        return

    if csv_output:
        rows = [library_section_to_csv(s) for s in sections]
        write_csv_to_output(rows, output)
        return

    table = Table(title="Plex Library Sections")
    table.add_column("Key", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Agent", style="blue")
    table.add_column("Scanner", style="magenta")
    table.add_column("Language", style="white")
    table.add_column("Count", style="magenta", justify="right")

    for sect in sections:
        table.add_row(
            sect.key,
            sect.title,
            sect.section_type.value if sect.section_type else "unknown",
            sect.agent or "-",
            sect.scanner or "-",
            sect.language or "-",
            str(sect.count),
        )

    console.print(table)


# --- Get section details -----------------------------------------------------


@library_app.command("get")
def get_section(
    section_key: str = typer.Argument(help="Section key to inspect"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Get details for a specific library section."""
    service = _get_service()
    section = service.get_section(section_key)

    if section is None:
        console.print(f"[red]Section not found: {section_key}[/red]")
        raise typer.Exit(code=1)

    if csv_output:
        rows = [library_section_to_csv(section)]
        write_csv_to_output(rows, output)
        return

    console.print(f"\n[bold]{section.title}[/bold]")
    console.print(f"  Key:          {section.key}")
    sect_type = section.section_type.value if section.section_type else "unknown"
    console.print(f"  Type:         {sect_type}")
    console.print(f"  Agent:        {section.agent or 'unknown'}")
    console.print(f"  Scanner:      {section.scanner or 'unknown'}")
    console.print(f"  Language:     {section.language or 'unknown'}")
    console.print(f"  Item Count:   {section.count}")
    console.print()


# --- Create section ----------------------------------------------------------


@library_app.command("create")
def create_section(
    name: str = typer.Option(..., "--name", help="Section name (e.g. 'Movies')"),
    section_type: str = typer.Option(
        ..., "--type", help="Content type: movie, show, artist, photo"
    ),
    agent: str = typer.Option(
        ..., "--agent", help="Metadata agent (e.g. com.plexapp.agents.imdb)"
    ),
    location: str = typer.Option(
        ..., "--location", help="Filesystem path for media content"
    ),
    language: str = typer.Option(
        "en", "--language", help="Language code (default: en)"
    ),
    scanner: str | None = typer.Option(
        None, "--scanner", help="Scanner name (auto-detected by type if omitted)"
    ),
) -> None:
    """Create a new library section.

    Example:
        plexctl library create --name "Movies" --type movie \\
            --agent "com.plexapp.agents.imdb" --location "/mnt/media/movies"
    """
    service = _get_service()
    section = service.create_section(
        name=name,
        section_type=section_type,
        agent=agent,
        location_path=location,
        language=language,
        scanner=scanner,
    )
    console.print(
        f"[green]✓ Created section '{section.title}' "
        f"(key={section.key}, type={section.section_type})[/green]"
    )


# --- Delete section ----------------------------------------------------------


@library_app.command("delete")
def delete_section(
    section_key: str = typer.Argument(help="Section key to delete"),
    confirm: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
) -> None:
    """Delete a library section permanently.

    This removes the section and all its metadata. Media files are not deleted.

    Example:
        plexctl library delete 2 --yes
    """
    if not confirm:
        console.print(
            f"[yellow]Will delete section {section_key}. Use --yes to confirm.[/yellow]"
        )
        raise typer.Exit(code=1)

    service = _get_service()
    service.delete_section(section_key)
    console.print(f"[green]✓ Deleted section {section_key}[/green]")


# --- Update section ----------------------------------------------------------


@library_app.command("update")
def update_section(
    section_key: str = typer.Argument(help="Section key to update"),
    name: str | None = typer.Option(None, "--name", help="New section name"),
    scanner: str | None = typer.Option(None, "--scanner", help="New scanner name"),
    agent: str | None = typer.Option(None, "--agent", help="New metadata agent"),
    language: str | None = typer.Option(None, "--language", help="New language code"),
    location: str | None = typer.Option(None, "--location", help="New filesystem path"),
) -> None:
    """Update a library section's settings.

    Only fields that are explicitly provided will be changed.

    Example:
        plexctl library update 2 --name "Films" --language fr
    """
    service = _get_service()
    section = service.update_section(
        section_key=section_key,
        name=name,
        scanner=scanner,
        agent=agent,
        language=language,
        location=location,
    )

    if section is None:
        console.print(f"[red]Failed to update section {section_key}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]✓ Updated section '{section.title}' (key={section.key})[/green]"
    )
    sect_type = section.section_type.value if section.section_type else "unknown"
    console.print(f"  Type:         {sect_type}")
    console.print(f"  Agent:        {section.agent or 'unknown'}")
    console.print(f"  Scanner:      {section.scanner or 'unknown'}")
    console.print(f"  Language:     {section.language or 'unknown'}")
    console.print(f"  Item Count:   {section.count}")




# --- Collections (sub-group) --------------------------------------------------

library_app.add_typer(collections_app, name="collections")

# --- Playlists (sub-group) ----------------------------------------------------

library_app.add_typer(playlists_app, name="playlists")
