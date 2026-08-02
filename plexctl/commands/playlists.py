"""Plex playlist management — regular and smart playlists.

Commands:
    plexctl playlists list          List regular playlists
    plexctl playlists get KEY       Get playlist details
    plexctl playlists create NAME   Create a playlist
    plexctl playlists update KEY    Update a playlist
    plexctl playlists delete KEY    Delete a playlist
    plexctl playlists items KEY     List items in a playlist
    plexctl playlists add KEY ITEMS Add items to a playlist
    plexctl playlists remove KEY ITEMS  Remove items from a playlist
    plexctl playlists smart ...     Smart playlist sub-commands
"""

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from plexctl.client import PlexClient
from plexctl.commands._helpers import if_empty_print, output_csv, require_confirm
from plexctl.config import load_config
from plexctl.converters import playlist_item_to_csv, playlist_to_csv, smart_playlist_to_csv
from plexctl.models import PlaylistType, SmartPlaylistFilter
from plexctl.options import CsvFlag, OutputFile
from plexctl.services.playlists import PlaylistService, SmartPlaylistService

# ---------------------------------------------------------------------------
# Typer apps
# ---------------------------------------------------------------------------

playlists_app = typer.Typer(
    name="playlists", help="Manage Plex playlists (regular and smart).", no_args_is_help=True
)

smart_app = typer.Typer(
    name="smart", help="Manage smart playlists with dynamic filters.", no_args_is_help=True
)

playlists_app.add_typer(smart_app, name="smart")

console = Console()

# ---------------------------------------------------------------------------
# Module-level option/argument singletons (Typer requirement)
# ---------------------------------------------------------------------------

CREATE_ITEMS_OPTION = typer.Option(
    [], "--item", "-i", help="Rating key(s) of items to add to the playlist"
)

ADD_ITEMS_ARGUMENT = typer.Argument(..., help="Rating keys of items to add")

REMOVE_ITEMS_ARGUMENT = typer.Argument(..., help="Rating keys of items to remove")

CREATE_FILTERS = typer.Option(
    ...,
    "--filter",
    "-f",
    help=(
        "Filter in FIELD=VALUE format "
        "(e.g. 'year>=2019', 'genre=Sci-Fi'). "
        "Use multiple --filter flags for AND conditions."
    ),
)

FilterList = Annotated[list[str], CREATE_FILTERS]

# ---------------------------------------------------------------------------
# Service factories
# ---------------------------------------------------------------------------


def _get_service() -> PlaylistService:
    """Load config and create a connected PlaylistService."""
    config = load_config()
    client = PlexClient(config)
    return PlaylistService(client)


def _get_smart_service() -> SmartPlaylistService:
    """Load config and create a connected SmartPlaylistService."""
    config = load_config()
    client = PlexClient(config)
    return SmartPlaylistService(client)


# ===================================================================
# Regular playlist commands
# ===================================================================

# --- List playlists ----------------------------------------------------------


@playlists_app.command("list")
def list_playlists(
    section: str | None = typer.Option(
        None, "--section", "-s", help="Section key to filter playlists"
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List all regular (non-smart) playlists.

    Example:
        plexctl playlists list
        plexctl playlists list --section 2
        plexctl playlists list --csv
    """
    service = _get_service()

    section_key = int(section) if section else None
    playlists = service.list_playlists(section_id=section_key)

    label = f" in section {section}" if section else ""
    if if_empty_print(playlists, f"No regular playlists found{label}."):
        return

    if output_csv(playlists, playlist_to_csv, csv_output, output):
        return

    table = Table(title="Playlists")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Items", style="magenta", justify="right")

    for pl in playlists:
        table.add_row(
            pl.key,
            pl.title,
            pl.playlist_type.value if pl.playlist_type else "unknown",
            str(pl.item_count),
        )

    console.print(table)


# --- Get playlist ------------------------------------------------------------


@playlists_app.command("get")
def get_playlist(
    key: str = typer.Argument(help="Playlist rating key"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Get detailed metadata for a regular playlist.

    Example:
        plexctl playlists get 12345
    """
    service = _get_service()
    playlist = service.get_playlist(key)

    if playlist is None:
        console.print(f"[red]Playlist not found: {key}[/red]")
        raise typer.Exit(code=1)

    if output_csv([playlist], playlist_to_csv, csv_output, output):
        return

    ptype = playlist.playlist_type.value if playlist.playlist_type else "unknown"
    console.print(f"\n[bold]{playlist.title}[/bold]")
    console.print(f"  Key:           {playlist.key}")
    console.print(f"  Type:          {ptype}")
    console.print(f"  Smart:         {'Yes' if playlist.smart else 'No'}")
    console.print(f"  Item Count:    {playlist.item_count}")


# --- Create playlist ---------------------------------------------------------


@playlists_app.command("create")
def create_playlist(
    name: str = typer.Argument(help="Playlist title"),
    type: str = typer.Option(
        "video", "--type", "-t", help="Playlist content type (video, audio, photo)"
    ),
    items: list[str] = CREATE_ITEMS_OPTION,
) -> None:
    """Create a new regular playlist.

    Optionally seed the playlist with items by specifying --item flags.

    Examples:
        plexctl playlists create "My Favorites"
        plexctl playlists create "My Favorites" -t video -i 12345 -i 12346
    """
    # Validate playlist type
    try:
        playlist_type = PlaylistType(type)
    except ValueError:
        available = ", ".join(t.value for t in PlaylistType)
        console.print(f"[red]Invalid type '{type}'. Available: {available}[/red]")
        raise typer.Exit(code=1) from None

    service = _get_service()
    item_keys = items if items else None
    try:
        result = service.create_playlist(
            title=name, playlist_type=playlist_type, item_keys=item_keys
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    item_msg = f" with {len(items)} item(s)" if items else ""
    console.print(
        f"[green]✓ Created playlist '{result.title}' " f"(key={result.key}){item_msg}[/green]"
    )


# --- Update playlist ---------------------------------------------------------


@playlists_app.command("update")
def update_playlist(
    key: str = typer.Argument(help="Playlist rating key"),
    title: str | None = typer.Option(None, "--title", "-t", help="New title for the playlist"),
) -> None:
    """Update a playlist's title.

    Example:
        plexctl playlists update 12345 --title "New Name"
    """
    if title is None:
        console.print("[yellow]Specify --title to update.[/yellow]")
        raise typer.Exit(code=1)

    service = _get_service()
    result = service.update_playlist(key, title=title)

    if result is None:
        console.print(f"[red]Failed to update playlist {key}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]✓ Updated playlist '{result.title}'[/green]")


# --- Delete playlist ---------------------------------------------------------


@playlists_app.command("delete")
def delete_playlist(
    key: str = typer.Argument(help="Playlist rating key"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a playlist permanently.

    The playlist's member items are not deleted from the library.

    Example:
        plexctl playlists delete 12345 --yes
    """
    require_confirm(confirm, f"delete playlist {key}")

    service = _get_service()
    service.delete_playlist(key)
    console.print(f"[green]✓ Deleted playlist {key}[/green]")


# --- List playlist items ----------------------------------------------------


@playlists_app.command("items")
def list_playlist_items(
    key: str = typer.Argument(help="Playlist rating key"),
    limit: int = typer.Option(100, "--limit", "-l", help="Maximum number of items to display"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List items contained in a playlist.

    Examples:
        plexctl playlists items 12345
        plexctl playlists items 12345 --limit 20
        plexctl playlists items 12345 --csv
    """
    service = _get_service()
    items = service.get_playlist_items(key, limit=limit)

    if if_empty_print(items, f"No items found in playlist {key}."):
        return

    if output_csv(items, playlist_item_to_csv, csv_output, output):
        return

    table = Table(title=f"Playlist Items ({key})")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Year", style="magenta", justify="right")
    table.add_column("Duration", style="blue", justify="right")

    for item in items:
        duration_str = _format_duration(item.duration) if item.duration else "-"
        table.add_row(
            item.key,
            item.title or "Unknown",
            item.media_type.value if item.media_type else "-",
            str(item.year) if item.year else "-",
            duration_str,
        )

    console.print(table)
    console.print(f"[dim]Showing {len(items)} items[/dim]")


# --- Add items to playlist -------------------------------------------------


@playlists_app.command("add")
def add_to_playlist(
    key: str = typer.Argument(help="Rating key of the playlist"),
    items: list[str] = ADD_ITEMS_ARGUMENT,
) -> None:
    """Add items to a playlist.

    Example:
        plexctl playlists add 12345 56789 56790
    """
    if not items:
        console.print("[yellow]No items specified.[/yellow]")
        raise typer.Exit(code=1)

    service = _get_service()
    try:
        count = service.add_items(key, items)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]✓ Added {count} item(s) to playlist {key}[/green]")


# --- Remove items from playlist ---------------------------------------------


@playlists_app.command("remove")
def remove_from_playlist(
    key: str = typer.Argument(help="Rating key of the playlist"),
    items: list[str] = REMOVE_ITEMS_ARGUMENT,
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Remove items from a playlist.

    Example:
        plexctl playlists remove 12345 56789 --yes
    """
    if not items:
        console.print("[yellow]No items specified.[/yellow]")
        raise typer.Exit(code=1)

    require_confirm(confirm, f"remove {len(items)} item(s) from playlist {key}")

    service = _get_service()
    try:
        count = service.remove_items(key, items)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]✓ Removed {count} item(s) from playlist {key}[/green]")


# ===================================================================
# Smart playlist commands (registered under smart_app sub-group)
# ===================================================================

# --- Create smart playlist ---------------------------------------------------


@smart_app.command("create")
def create_smart_playlist(
    name: str = typer.Argument(help="Smart playlist title"),
    type: str = typer.Option(
        "video", "--type", "-t", help="Playlist content type (video, audio, photo)"
    ),
    section: str | None = typer.Option(
        None, "--section", "-s", help="Library section key to scope the query"
    ),
    filter: FilterList = None,  # type: ignore[assignment]
    sort: str | None = typer.Option(
        None, "--sort", help="Sort order (e.g. 'year:desc', 'titleSort:asc')"
    ),
    limit: int = typer.Option(
        100, "--limit", "-l", help="Maximum number of items in the playlist"
    ),
) -> None:
    """Create a new smart playlist with dynamic query filters.

    Smart playlists use filter conditions that automatically update
    when library content changes.

    Examples:
        plexctl playlists smart create "Recent Sci-Fi" -t video \\
            -f "year>=2019" -f "genre=Sci-Fi"
        plexctl playlists smart create "Action Movies" -t video \\
            -f "genre=Action" --sort "year:desc"
        plexctl playlists smart create "80s Music" -t audio \\
            -f "year>=1980" -f "year<=1989"
    """
    parsed_filters = _parse_filter_strings(filter)

    if not parsed_filters:
        console.print("[red]At least one --filter is required.[/red]")
        raise typer.Exit(code=1)

    # Validate playlist type
    try:
        playlist_type = PlaylistType(type)
    except ValueError:
        available = ", ".join(t.value for t in PlaylistType)
        console.print(f"[red]Invalid type '{type}'. Available: {available}[/red]")
        raise typer.Exit(code=1) from None

    service = _get_smart_service()
    try:
        result = service.create_smart_playlist(
            name=name,
            filters=parsed_filters,
            playlist_type=playlist_type,
            section_id=section,
            sort=sort,
            limit=limit,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    filter_summary = ", ".join(f"{f.field}{f.operator}{f.value}" for f in parsed_filters)
    console.print(
        f"[green]✓ Created smart playlist '{result.title}' "
        f"(key={result.key}, filters: {filter_summary})[/green]"
    )


# --- Get smart playlist ------------------------------------------------------


@smart_app.command("get")
def get_smart_playlist(
    key: str = typer.Argument(help="Smart playlist rating key"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Get detailed metadata for a smart playlist.

    Example:
        plexctl playlists smart get 12345
    """
    service = _get_smart_service()
    playlist = service.get_smart_playlist(key)

    if playlist is None:
        console.print(f"[red]Smart playlist not found: {key}[/red]")
        raise typer.Exit(code=1)

    if output_csv([playlist], smart_playlist_to_csv, csv_output, output):
        return

    ptype = playlist.playlist_type.value if playlist.playlist_type else "unknown"
    console.print(f"\n[bold]{playlist.title}[/bold]")
    console.print(f"  Key:           {playlist.key}")
    console.print(f"  Type:          {ptype}")
    console.print(f"  Smart:         {'Yes' if playlist.smart else 'No'}")
    console.print(f"  Item Count:    {playlist.item_count}")

    if playlist.filters:
        console.print("\n  [bold]Filters:[/bold]")
        for filt in playlist.filters:
            console.print(f"    {filt.field} {filt.operator} {filt.value}")


# --- List smart playlists ----------------------------------------------------


@smart_app.command("list")
def list_smart_playlists(
    section: str | None = typer.Option(
        None, "--section", "-s", help="Section key to filter smart playlists"
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List all smart playlists, optionally filtered by section.

    Example:
        plexctl playlists smart list
        plexctl playlists smart list --section 2
        plexctl playlists smart list --csv
    """
    service = _get_smart_service()

    section_key = int(section) if section else None
    playlists = service.list_smart_playlists(section_id=section_key)

    label = f" in section {section}" if section else ""
    if if_empty_print(playlists, f"No smart playlists found{label}."):
        return

    if output_csv(playlists, smart_playlist_to_csv, csv_output, output):
        return

    table = Table(title="Smart Playlists")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Items", style="magenta", justify="right")
    table.add_column("Filters", style="blue")

    for pl in playlists:
        filter_summary = (
            ", ".join(f"{f.field}{f.operator}{f.value}" for f in pl.filters)
            if pl.filters
            else "-"
        )
        table.add_row(
            pl.key,
            pl.title,
            pl.playlist_type.value if pl.playlist_type else "unknown",
            str(pl.item_count),
            filter_summary,
        )

    console.print(table)


# --- Update smart playlist ---------------------------------------------------


@smart_app.command("update")
def update_smart_playlist(
    key: str = typer.Argument(help="Smart playlist rating key"),
    name: str | None = typer.Option(None, "--name", "-n", help="New title for the playlist"),
    filter: list[str] = typer.Option(  # noqa: B008
        [],
        "--filter",
        "-f",
        help="New filter in FIELD=VALUE format. Replaces all existing filters.",
    ),
    sort: str | None = typer.Option(None, "--sort", help="New sort order"),
) -> None:
    """Update a smart playlist's title, filters, or sort order.

    When --filter is specified, it replaces ALL existing filters.
    To keep existing filters, include them in the new --filter flags.

    Examples:
        plexctl playlists smart update 12345 --name "Updated Title"
        plexctl playlists smart update 12345 --filter "year>=2020" --filter "genre=Sci-Fi"
    """
    if name is None and not filter and sort is None:
        console.print("[yellow]Specify at least --name, --filter, or --sort to update.[/yellow]")
        raise typer.Exit(code=1)

    service = _get_smart_service()

    parsed_filters = None
    if filter:
        parsed_filters = _parse_filter_strings(filter)
        if not parsed_filters:
            console.print("[red]Could not parse any valid filters.[/red]")
            raise typer.Exit(code=1)

    result = service.update_smart_playlist(key, name=name, filters=parsed_filters, sort=sort)

    if result is None:
        console.print(f"[red]Failed to update smart playlist {key}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]✓ Updated smart playlist '{result.title}'[/green]")


# --- Delete smart playlist ---------------------------------------------------


@smart_app.command("delete")
def delete_smart_playlist(
    key: str = typer.Argument(help="Smart playlist rating key"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a smart playlist permanently.

    The matching media items are not deleted.

    Example:
        plexctl playlists smart delete 12345 --yes
    """
    require_confirm(confirm, f"delete smart playlist {key}")

    service = _get_smart_service()
    service.delete_smart_playlist(key)
    console.print(f"[green]✓ Deleted smart playlist {key}[/green]")


# --- List smart playlist items ------------------------------------------------


@smart_app.command("items")
def list_smart_playlist_items(
    key: str = typer.Argument(help="Smart playlist rating key"),
    limit: int = typer.Option(100, "--limit", "-l", help="Maximum number of items to display"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List items contained in a smart playlist.

    Shows the media items that match the smart playlist's filter conditions.

    Examples:
        plexctl playlists smart items 12345
        plexctl playlists smart items 12345 --limit 20
        plexctl playlists smart items 12345 --csv
    """
    service = _get_smart_service()
    items = service.get_playlist_items(key, limit=limit)

    if if_empty_print(items, f"No items found in playlist {key}."):
        return

    if output_csv(items, playlist_item_to_csv, csv_output, output):
        return

    table = Table(title=f"Playlist Items ({key})")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Year", style="magenta", justify="right")
    table.add_column("Duration", style="blue", justify="right")

    for item in items:
        duration_str = _format_duration(item.duration) if item.duration else "-"
        table.add_row(
            item.key,
            item.title or "Unknown",
            item.media_type.value if item.media_type else "-",
            str(item.year) if item.year else "-",
            duration_str,
        )

    console.print(table)
    console.print(f"[dim]Showing {len(items)} items[/dim]")


# ===================================================================
# Helper functions
# ===================================================================


def _parse_filter_strings(filter_strings: list[str]) -> list[SmartPlaylistFilter]:
    """Parse CLI filter strings like 'year>=2019' into SmartPlaylistFilter objects.

    Supports operators: =, !=, >=, <=, >, <, contains

    Args:
        filter_strings: List of filter strings from the CLI.

    Returns:
        List of parsed SmartPlaylistFilter objects.
    """
    operators = [">=", "<=", "!=", ">", "<", "=", "contains"]

    filters: list[SmartPlaylistFilter] = []
    for raw in filter_strings:
        # Try each operator from longest to shortest to avoid partial matches
        for op in operators:
            if op in raw:
                parts = raw.split(op, 1)
                if len(parts) == 2 and parts[0] and parts[1]:
                    filters.append(
                        SmartPlaylistFilter(
                            field=parts[0].strip(), operator=op, value=parts[1].strip()
                        )
                    )
                    break
        else:
            # No operator found — report but skip
            console.print(
                f"[yellow]Warning: Could not parse filter '{raw}'. "
                f"Expected format: FIELD=VALUE or FIELD>=VALUE[/yellow]"
            )

    return filters


def _format_duration(milliseconds: int | None) -> str:
    """Format a duration in milliseconds to a human-readable string.

    Args:
        milliseconds: Duration in milliseconds.

    Returns:
        Formatted duration string (e.g. '1h 42m', '45m').
    """
    if milliseconds is None or milliseconds <= 0:
        return "-"

    total_seconds = milliseconds // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60

    if hours > 0:
        return f"{hours}h {minutes}m"

    return f"{minutes}m"
