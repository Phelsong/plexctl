"""Photo browsing commands for plexctl.

Provides commands for listing and exploring photo libraries:
- List photo albums in a section (default)
- List photos (optionally filtered by album)
- Tree view of a photo section
- Recently added photo albums

Examples:
    plexctl photos                      # List albums in default section
    plexctl photos --tree               # Tree view with (key) labels
    plexctl photos --section "My Photos" # Specify a different section
    plexctl photos list                 # List all photos
    plexctl photos list --album 12345   # List photos in a specific album
    plexctl photos recently-added       # Recently added photo albums
"""

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from plexctl.client import PlexClient
from plexctl.commands._helpers import if_empty_print, output_csv, require_section_key
from plexctl.config import load_config
from plexctl.converters import media_tree_item_to_csv, photo_album_to_csv, photo_info_to_csv
from plexctl.models import PhotoAlbumInfo, PhotoInfo
from plexctl.options import CsvFlag, OutputFile
from plexctl.services.photos import PhotoService
from plexctl.services.tree import TreeService

photos_app = typer.Typer(
    name="photos", help="Browse and manage photo libraries.", no_args_is_help=True
)
console = Console()


def _get_photo_service() -> PhotoService:
    """Load config and create a connected PhotoService."""
    config = load_config()
    client = PlexClient(config)
    return PhotoService(client)


def _get_tree_service() -> TreeService:
    """Load config and create a connected TreeService."""
    config = load_config()
    client = PlexClient(config)
    return TreeService(client)


def _render_album_table(albums: list[PhotoAlbumInfo], section: str) -> None:
    """Render photo albums as a Rich table."""
    table = Table(title=f"Photo Albums in {section}")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Photos", style="yellow", justify="right")
    table.add_column("Rating", style="magenta", justify="right")

    for album in albums:
        table.add_row(
            album.key,
            album.title or "Unknown",
            str(album.photo_count),
            f"{album.user_rating:.1f}" if album.user_rating else "-",
        )

    console.print(table)


def _render_photo_table(photos: list[PhotoInfo]) -> None:
    """Render photos as a Rich table."""
    table = Table(title="Photos")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Album", style="yellow")
    table.add_column("Date", style="blue")

    for photo in photos:
        table.add_row(
            photo.key,
            photo.title or "Unknown",
            photo.album or "-",
            photo.originally_available or "-",
        )

    console.print(table)


def _render_album_tree(albums: list[PhotoAlbumInfo]) -> Tree:
    """Render photo albums as a Rich Tree with (key) labels."""
    tree = Tree("[bold]Photos[/bold]")
    for album in albums:
        count = f"({album.photo_count} photos)" if album.photo_count else ""
        count_label = f" [dim]{count}[/dim]" if count else ""
        label = f"{album.title or album.key}{count_label} [dim](key={album.key})[/dim]"
        tree.add(label)
    return tree


# --- Default callback (list albums) ----------------------------------------


@photos_app.callback(invoke_without_command=True)
def photos_default(
    ctx: typer.Context,
    section: str = typer.Option("Photos", "--section", "-s", help="Library section name"),
    limit: int = typer.Option(
        25, "--limit", "-l", help="Maximum number of results (list view only)"
    ),
    tree: bool = typer.Option(False, "--tree", "-t", help="Display as a tree with rating keys"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Browse photo albums in your library.

    Examples:
        plexctl photos                      # List albums in default section
        plexctl photos --tree               # Tree view with (key) labels
        plexctl photos --section "My Photos"
    """
    if ctx.invoked_subcommand is not None:
        return

    service = _get_photo_service()
    albums = service.list_albums(section_title=section)

    if if_empty_print(albums, f"No photo albums found in section '{section}'"):
        return

    if tree:
        tree_service = _get_tree_service()
        section_key = require_section_key(tree_service, section)

        items = tree_service.get_section_tree(section_key, media_type="photo")
        if if_empty_print(items, f"No items found in section '{section}'"):
            return

        if output_csv(items, media_tree_item_to_csv, csv_output, output):
            return

        rich_tree = Tree(f"[bold]{section}[/bold]")
        for item in items:
            mtype = item.media_type.value if item.media_type else ""
            type_label = f" [dim]{mtype}[/dim]" if mtype else ""
            year_label = f" [dim]({item.year})[/dim]" if item.year else ""
            key_label = f" [dim](key={item.key})[/dim]"
            node_label = f"{item.title or item.key}{type_label}{year_label}{key_label}"
            rich_tree.add(node_label)
        console.print(rich_tree)
        return

    if output_csv(albums[:limit], photo_album_to_csv, csv_output, output):
        return

    _render_album_table(albums[:limit], section)
    if len(albums) > limit:
        console.print(
            f"[dim]Showing {limit} of {len(albums)} albums. " f"Use --limit to see more.[/dim]"
        )


# --- List subcommand --------------------------------------------------------


@photos_app.command("list")
def photos_list(
    section: str = typer.Option("Photos", "--section", "-s", help="Library section name"),
    album_key: str | None = typer.Option(
        None, "--album", "-a", help="Rating key of a photo album to filter by"
    ),
    limit: int = typer.Option(25, "--limit", "-l", help="Maximum number of results"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List photos, optionally filtered by album.

    Examples:
        plexctl photos list                  # List all photos in section
        plexctl photos list --album 12345    # List photos in a specific album
    """
    service = _get_photo_service()
    photos = service.list_photos(section_title=section, album_key=album_key, limit=limit)

    empty_msg = (
        f"No photos found in album '{album_key}'"
        if album_key
        else f"No photos found in section '{section}'"
    )
    if if_empty_print(photos, empty_msg):
        return

    if output_csv(photos[:limit], photo_info_to_csv, csv_output, output):
        return

    _render_photo_table(photos[:limit])
    if len(photos) > limit:
        console.print(
            f"[dim]Showing {limit} of {len(photos)} photos. " f"Use --limit to see more.[/dim]"
        )


# --- Tree subcommand --------------------------------------------------------


@photos_app.command("tree")
def photos_tree(
    section: str = typer.Option(
        "Photos", "--section", "-s", help="Section name or key to browse (e.g. 'Photos', '1')"
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Browse a photo library section as a hierarchical tree.

    Examples:
        plexctl photos tree -s Photos
        plexctl photos tree -s 4
    """
    tree_service = _get_tree_service()
    section_key = require_section_key(tree_service, section)

    items = tree_service.get_section_tree(section_key, media_type="photo")

    if if_empty_print(items, f"No items found in section '{section}'"):
        return

    if output_csv(items, media_tree_item_to_csv, csv_output, output):
        return

    rich_tree = Tree(f"[bold]Section {section}[/bold]")
    for item in items:
        mtype = item.media_type.value if item.media_type else ""
        type_label = f" [dim]{mtype}[/dim]" if mtype else ""
        year_label = f" [dim]({item.year})[/dim]" if item.year else ""
        leaf_label = f" [dim]({item.leaf_count} items)[/dim]" if item.leaf_count else ""
        key_label = f" [dim](key={item.key})[/dim]"
        node_label = f"{item.title or item.key}{type_label}{year_label}{leaf_label}{key_label}"
        rich_tree.add(node_label)
    console.print(rich_tree)


# --- Recently added subcommand ----------------------------------------------


@photos_app.command("recently-added")
def photos_recently_added(
    section: str = typer.Option("Photos", "--section", "-s", help="Library section name"),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum number of results"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List recently added photo albums.

    Examples:
        plexctl photos recently-added
        plexctl photos recently-added --limit 20
    """
    service = _get_photo_service()
    albums = service.recently_added(section_title=section, maxresults=limit)

    if if_empty_print(albums, f"No recently added albums in section '{section}'"):
        return

    if output_csv(albums, photo_album_to_csv, csv_output, output):
        return

    _render_album_table(albums, section)
