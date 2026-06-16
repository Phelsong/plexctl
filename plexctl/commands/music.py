"""Music browsing commands for plexctl.

Provides commands for listing and exploring music libraries:
- List all artists in a section (default)
- Tree view with --tree flag, showing rating keys
- Browse albums and tracks with filtering
- Recently added music

Examples:
    plexctl music                          # List artists in default section
    plexctl music --tree                   # Tree view with (key) labels
    plexctl music --section "My Music"     # Specify a different section
    plexctl music albums                   # List albums in default section
    plexctl music albums --artist 12345    # List albums by a specific artist
    plexctl music tracks --album 67890     # List tracks in a specific album
    plexctl music tree -s "Music"          # Browse section as tree
    plexctl music recently-added           # Recently added music
"""

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from plexctl.client import PlexClient
from plexctl.config import load_config
from plexctl.converters import album_info_to_csv, artist_info_to_csv, track_info_to_csv
from plexctl.csv_utils import write_csv_to_output
from plexctl.models import AlbumInfo, ArtistInfo, MediaTreeItem, TrackInfo
from plexctl.options import CsvFlag, OutputFile
from plexctl.services.music import MusicService
from plexctl.services.tree import TreeService

music_app = typer.Typer(
    name="music", help="Browse and manage music libraries.", invoke_without_command=True
)
console = Console()


def _get_service() -> MusicService:
    """Load config and create a connected MusicService."""
    config = load_config()
    client = PlexClient(config)
    return MusicService(client)


def _get_tree_service() -> TreeService:
    """Load config and create a connected TreeService."""
    config = load_config()
    client = PlexClient(config)
    return TreeService(client)


def _format_duration(duration_ms: int | None) -> str:
    """Format a duration in milliseconds as M:SS."""
    if duration_ms is None or duration_ms <= 0:
        return "-"
    total_seconds = duration_ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def _render_artist_tree(items: list[MediaTreeItem]) -> Tree:
    """Render artists as a rich Tree with (key) labels."""
    tree = Tree("[bold]Artists[/bold]")
    for item in items:
        year_label = ""
        key_label = f" [dim](key={item.key})[/dim]"
        label = f"{item.title or item.key}{year_label}{key_label}"
        tree.add(label)
    return tree


# --- Default callback (list artists) ----------------------------------------


@music_app.callback(invoke_without_command=True)
def music_default(
    ctx: typer.Context,
    section: str = typer.Option("Music", "--section", "-s", help="Library section name"),
    limit: int = typer.Option(
        25, "--limit", "-l", help="Maximum number of results (list view only)"
    ),
    tree: bool = typer.Option(False, "--tree", "-t", help="Display as a tree with rating keys"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Browse and manage music libraries.

    Without a subcommand, lists artists in the section.

    Examples:
        plexctl music                      # List artists in default section
        plexctl music --tree               # Tree view with (key) labels
        plexctl music --section "My Music" # Specify a different section
    """
    if ctx.invoked_subcommand is not None:
        return

    service = _get_service()
    artists = service.list_artists(section_title=section, limit=limit)

    if not artists:
        console.print(f"[dim]No artists found in section '{section}'[/dim]")
        return

    if tree:
        tree_service = _get_tree_service()
        section_key = tree_service.resolve_section_key(section)
        if section_key is None:
            console.print(f"[red]Section not found: {section}[/red]")
            console.print("[dim]Use 'plexctl library list' to see available sections.[/dim]")
            raise typer.Exit(code=1)

        items = tree_service.get_section_tree(section_key, media_type="artist")
        if not items:
            console.print(f"[dim]No artists found in section '{section}'[/dim]")
            return

        if csv_output:
            from plexctl.converters import media_tree_item_to_csv

            rows = [media_tree_item_to_csv(i) for i in items]
            write_csv_to_output(rows, output)
            return

        rich_tree = _render_artist_tree(items)
        console.print(rich_tree)
        return

    if csv_output:
        rows: list[BaseModel] = [artist_info_to_csv(a) for a in artists[:limit]]  # type: ignore[no-redef]
        write_csv_to_output(rows, output)
        return

    table = Table(title=f"Artists in {section}")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Genre", style="yellow")
    table.add_column("Country", style="blue")
    table.add_column("Albums", style="magenta", justify="right")

    for artist in artists[:limit]:
        table.add_row(
            artist.key,
            artist.title or "Unknown",
            artist.genre or "-",
            artist.country or "-",
            str(artist.album_count) if artist.album_count else "-",
        )

    console.print(table)
    if len(artists) > limit:
        console.print(
            f"[dim]Showing {limit} of {len(artists)} artists. " f"Use --limit to see more.[/dim]"
        )


# --- Albums subcommand -------------------------------------------------------


@music_app.command("albums")
def music_albums(
    section: str = typer.Option("Music", "--section", "-s", help="Library section name"),
    artist_key: str | None = typer.Option(
        None, "--artist", "-a", help="Filter by artist rating key"
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum number of results"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List albums, optionally filtered by artist.

    Examples:
        plexctl music albums                  # List all albums
        plexctl music albums --artist 12345   # Albums by a specific artist
    """
    service = _get_service()
    albums = service.list_albums(section_title=section, artist_key=artist_key, limit=limit)

    if not albums:
        if artist_key:
            console.print(f"[dim]No albums found for artist key '{artist_key}'[/dim]")
        else:
            console.print(f"[dim]No albums found in section '{section}'[/dim]")
        return

    if csv_output:
        rows = [album_info_to_csv(a) for a in albums]
        write_csv_to_output(rows, output)
        return

    table = Table(title="Albums" if not artist_key else f"Albums (artist {artist_key})")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Artist", style="yellow")
    table.add_column("Year", style="magenta", justify="right")
    table.add_column("Tracks", style="blue", justify="right")

    for album in albums:
        table.add_row(
            album.key,
            album.title or "Unknown",
            album.artist or "-",
            str(album.year) if album.year else "-",
            str(album.track_count) if album.track_count else "-",
        )

    console.print(table)


# --- Tracks subcommand -------------------------------------------------------


@music_app.command("tracks")
def music_tracks(
    section: str = typer.Option("Music", "--section", "-s", help="Library section name"),
    album_key: str | None = typer.Option(
        None, "--album", "-a", help="Filter by album rating key"
    ),
    artist_key: str | None = typer.Option(
        None, "--artist", "-A", help="Filter by artist rating key"
    ),
    limit: int = typer.Option(100, "--limit", "-l", help="Maximum number of results"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List tracks, optionally filtered by album or artist.

    Examples:
        plexctl music tracks                   # List all tracks
        plexctl music tracks --album 67890      # Tracks in a specific album
        plexctl music tracks --artist 12345     # Tracks by a specific artist
    """
    service = _get_service()
    tracks = service.list_tracks(
        section_title=section, album_key=album_key, artist_key=artist_key, limit=limit
    )

    if not tracks:
        filter_desc = ""
        if album_key:
            filter_desc = f" in album '{album_key}'"
        elif artist_key:
            filter_desc = f" by artist '{artist_key}'"
        console.print(f"[dim]No tracks found{filter_desc}[/dim]")
        return

    if csv_output:
        rows = [track_info_to_csv(t) for t in tracks]
        write_csv_to_output(rows, output)
        return

    title = "Tracks"
    if album_key:
        title = f"Tracks (album {album_key})"
    elif artist_key:
        title = f"Tracks (artist {artist_key})"

    table = Table(title=title)
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Artist", style="yellow")
    table.add_column("Album", style="blue")
    table.add_column("#", style="magenta", justify="right")
    table.add_column("Duration", style="white", justify="right")

    for track in tracks:
        table.add_row(
            track.key,
            track.title or "Unknown",
            track.artist or "-",
            track.album or "-",
            str(track.track_number) if track.track_number else "-",
            _format_duration(track.duration),
        )

    console.print(table)


# --- Tree subcommand ----------------------------------------------------------


@music_app.command("tree")
def music_tree(
    section: str = typer.Option(
        ..., "--section", "-s", help="Section name or key to browse (e.g. '3', 'Music')"
    ),
    media_type: str | None = typer.Option(
        None, "--type", "-t", help="Filter by type: artist, album, track"
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Browse a music library section as a hierarchical tree.

    Examples:
        plexctl music tree -s "Music"
        plexctl music tree -s "Music" --type artist
    """
    service = _get_tree_service()
    section_key = service.resolve_section_key(section)

    if section_key is None:
        console.print(f"[red]Section not found: {section}[/red]")
        console.print("[dim]Use 'plexctl library list' to see available sections.[/dim]")
        raise typer.Exit(code=1)

    items = service.get_section_tree(section_key, media_type=media_type)

    if not items:
        console.print(f"[dim]No items found in section '{section}'[/dim]")
        return

    if csv_output:
        from plexctl.converters import media_tree_item_to_csv

        rows = [media_tree_item_to_csv(i) for i in items]
        write_csv_to_output(rows, output)
        return

    # Reuse the nav tree rendering from shows
    from plexctl.commands.shows import _render_nav_tree

    rich_tree = Tree(f"[bold]Section {section}[/bold]")
    _render_nav_tree(rich_tree, items)
    console.print(rich_tree)


# --- Recently Added subcommand ----------------------------------------------


@music_app.command("recently-added")
def music_recently_added(
    section: str = typer.Option("Music", "--section", "-s", help="Library section name"),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum number of results"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Show recently added music.

    Examples:
        plexctl music recently-added           # Recent additions (default section)
        plexctl music recently-added -s "Rock" # Recent additions in Rock section
    """
    service = _get_service()
    items = service.recently_added(section_title=section, maxresults=limit)

    if not items:
        console.print(f"[dim]No recently added music in section '{section}'[/dim]")
        return

    if csv_output:
        rows: list[BaseModel] = []
        for item in items:
            if isinstance(item, ArtistInfo):
                rows.append(artist_info_to_csv(item))
            elif isinstance(item, AlbumInfo):
                rows.append(album_info_to_csv(item))
            elif isinstance(item, TrackInfo):
                rows.append(track_info_to_csv(item))
        write_csv_to_output(rows, output)
        return

    table = Table(title=f"Recently Added Music in {section}")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Type", style="blue")
    table.add_column("Title", style="green")
    table.add_column("Artist", style="yellow")
    table.add_column("Year", style="magenta", justify="right")

    for item in items:
        item_type = "artist"
        artist = "-"
        year = "-"
        if isinstance(item, AlbumInfo):
            item_type = "album"
            artist = item.artist or "-"
            year = str(item.year) if item.year else "-"
        elif isinstance(item, TrackInfo):
            item_type = "track"
            artist = item.artist or "-"
            year = str(item.year) if item.year else "-"
        elif isinstance(item, ArtistInfo):
            year = "-"

        table.add_row(item.key, item_type, item.title or "Unknown", artist, year)

    console.print(table)
