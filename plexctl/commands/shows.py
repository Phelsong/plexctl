"""TV shows browsing commands for plexctl.

Provides commands for listing and exploring TV shows:
- List all shows in a section (default)
- Tree view with --tree flag, showing rating keys
- Drill into a specific show's seasons with a rating key argument
- Tree subcommands for hierarchical navigation:
  - tree: Browse a section as a tree
  - show: Show seasons and episodes for a show
  - season: Show episodes in a season

Examples:
    plexctl shows                      # List shows in default section
    plexctl shows --tree               # Tree view with (key) labels
    plexctl shows --section Anime      # Specify a different section
    plexctl shows 12345                # List seasons for show 12345
    plexctl shows 12345 --tree         # Tree view of show's seasons
    plexctl shows tree -s "TV Shows"   # Browse section as tree
    plexctl shows show 12345            # Show seasons/episodes tree
    plexctl shows season 54321         # Show episodes tree
"""

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from plexctl.client import PlexClient
from plexctl.commands._helpers import if_empty_print, output_csv, require_section_key
from plexctl.config import load_config
from plexctl.converters import media_metadata_to_csv, media_tree_item_to_csv
from plexctl.csv_utils import write_csv_to_output
from plexctl.models import MediaTreeItem
from plexctl.options import CsvFlag, OutputFile
from plexctl.services.metadata import MetadataService
from plexctl.services.tree import TreeService

shows_app = typer.Typer(
    name="shows", help="Browse TV shows in your library.", invoke_without_command=True
)
console = Console()


def _get_metadata_service() -> MetadataService:
    """Load config and create a connected MetadataService."""
    config = load_config()
    client = PlexClient(config)
    return MetadataService(client)


def _get_tree_service() -> TreeService:
    """Load config and create a connected TreeService."""
    config = load_config()
    client = PlexClient(config)
    return TreeService(client)


def _build_item_label(item: MediaTreeItem, show_type: bool = True) -> str:
    """Build a display label for a tree item with (key) suffix."""
    parts: list[str] = [item.title or item.key]
    if show_type and item.media_type:
        parts.append(f"[dim]{item.media_type.value}[/dim]")
    if item.year:
        parts.append(f"[dim]({item.year})[/dim]")
    if item.leaf_count:
        parts.append(f"[dim]({item.leaf_count} items)[/dim]")
    parts.append(f"[dim](key={item.key})[/dim]")
    return " ".join(parts)


def _render_tree(items: list[MediaTreeItem]) -> Tree:
    """Render media items as a rich Tree with (key) labels."""
    tree = Tree("[bold]Shows[/bold]")
    for item in items:
        label = _build_item_label(item, show_type=False)
        node = tree.add(label)
        if item.children:
            _add_children(node, item.children)
    return tree


def _add_children(parent_node: Tree, children: list[MediaTreeItem]) -> None:
    """Recursively add children to a tree node with (key) labels."""
    for child in children:
        label = _build_item_label(child)
        node = parent_node.add(label)
        if child.children:
            _add_children(node, child.children)


def _render_nav_tree(
    parent: Tree, items: list[MediaTreeItem], depth: int = 0, max_depth: int | None = None
) -> None:
    """Render media tree items as rich Tree nodes with depth control.

    Unlike _render_tree which builds a full Tree object, this appends
    children to an existing Tree node and supports max_depth limiting.

    Args:
        parent: Rich Tree node to add children to.
        items: List of MediaTreeItem to render.
        depth: Current nesting depth.
        max_depth: Maximum depth to render (None for unlimited).
    """
    if max_depth is not None and depth >= max_depth:
        return

    for item in items:
        type_label = f"[dim]{item.media_type.value}[/dim]" if item.media_type else ""
        count_label = f" [dim]({item.leaf_count} items)[/dim]" if item.leaf_count else ""
        year_label = f" [dim]({item.year})[/dim]" if item.year else ""
        key_label = f" [dim](key={item.key})[/dim]"
        label = f"{item.title or item.key} {type_label}{year_label}{count_label}{key_label}"

        node = parent.add(label)
        if item.children:
            _render_nav_tree(node, item.children, depth + 1, max_depth)


def _render_show_seasons_tree(show: MediaTreeItem) -> Tree:
    """Render a show's seasons as a rich Tree with (key) labels."""
    tree = Tree(f"[bold]{show.title or show.key}[/bold]")
    _add_children(tree, show.children)
    return tree


def _flatten_tree(
    items: list[MediaTreeItem], result: list[MediaTreeItem] | None = None
) -> list[MediaTreeItem]:
    """Flatten a nested tree into a flat list for CSV export."""
    if result is None:
        result = []
    for item in items:
        result.append(item)
        if item.children:
            _flatten_tree(item.children, result)
    return result


@shows_app.callback(invoke_without_command=True)
def shows_default(
    ctx: typer.Context,
    rating_key: str | None = typer.Argument(
        default=None, help="Rating key of a show to list its seasons"
    ),
    section: str = typer.Option("TV Shows", "--section", "-s", help="Library section name"),
    limit: int = typer.Option(
        25, "--limit", "-l", help="Maximum number of results (list view only)"
    ),
    tree: bool = typer.Option(False, "--tree", "-t", help="Display as a tree with rating keys"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Browse TV shows in your library.

    Without a rating key, lists shows in the section.
    With a rating key, lists seasons for that show.

    Examples:
        plexctl shows                      # List shows in default section
        plexctl shows --tree               # Tree view with (key) labels
        plexctl shows --section Anime      # Specify a different section
        plexctl shows 12345                # List seasons for show 12345
        plexctl shows 12345 --tree         # Tree view of show's seasons
    """
    # If a subcommand was specified, let it handle things
    if ctx.invoked_subcommand is not None:
        return

    if rating_key is not None:
        _show_seasons(rating_key, tree=tree, csv_output=csv_output, output=output)
        return

    _list_shows(section=section, limit=limit, tree=tree, csv_output=csv_output, output=output)


def _list_shows(
    section: str, limit: int, tree: bool, csv_output: bool, output: str | None
) -> None:
    """List shows in a library section."""
    service = _get_metadata_service()
    all_shows = service.get_all_shows(section)

    if if_empty_print(all_shows, f"No shows found in section '{section}'"):
        return

    if tree:
        tree_service = _get_tree_service()
        section_key = require_section_key(tree_service, section)

        items = tree_service.get_section_tree(section_key, media_type="show")
        if if_empty_print(items, f"No shows found in section '{section}'"):
            return

        if output_csv(_flatten_tree(items), media_tree_item_to_csv, csv_output, output):
            return

        rich_tree = _render_tree(items)
        console.print(rich_tree)
        return

    if output_csv(all_shows[:limit], media_metadata_to_csv, csv_output, output):
        return

    table = Table(title=f"TV Shows in {section}")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Year", style="yellow", justify="right")
    table.add_column("Rating", style="magenta", justify="right")

    for show in all_shows[:limit]:
        table.add_row(
            show.key,
            show.title or "Unknown",
            str(show.year) if show.year else "-",
            f"{show.audience_rating:.1f}" if show.audience_rating else "-",
        )

    console.print(table)
    if len(all_shows) > limit:
        console.print(
            f"[dim]Showing {limit} of {len(all_shows)} shows. " f"Use --limit to see more.[/dim]"
        )


def _show_seasons(rating_key: str, tree: bool, csv_output: bool, output: str | None) -> None:
    """List seasons for a specific show."""
    tree_service = _get_tree_service()
    show = tree_service.get_show_tree(rating_key)

    if show is None:
        console.print(f"[red]Show not found: {rating_key}[/red]")
        raise typer.Exit(code=1)

    if not show.children:
        console.print(f"[dim]No seasons found for '{show.title or rating_key}'[/dim]")
        return

    if tree:
        if csv_output:
            rows = [media_tree_item_to_csv(show)]
            rows.extend(media_tree_item_to_csv(i) for i in _flatten_tree(show.children))
            write_csv_to_output(rows, output)
            return

        rich_tree = _render_show_seasons_tree(show)
        console.print(rich_tree)
        return

    if csv_output:
        rows = [media_tree_item_to_csv(show)]
        rows.extend(media_tree_item_to_csv(i) for i in show.children)
        write_csv_to_output(rows, output)
        return

    table = Table(title=show.title or f"Show {rating_key}")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Season", style="green")
    table.add_column("Episodes", style="yellow", justify="right")

    for season in show.children:
        episodes_label = str(season.leaf_count) if season.leaf_count else "-"
        table.add_row(season.key, season.title or "Unknown", episodes_label)

    console.print(table)


# --- Tree navigation subcommands -----------------------------------------------


@shows_app.command("tree")
def shows_tree(
    section: str = typer.Option(
        ...,
        "--section",
        "-s",
        help="Section name or key to browse (e.g. 'shows', 'TV Shows', '2')",
    ),
    media_type: str | None = typer.Option(
        None, "--type", "-t", help="Filter by type: show, movie, artist, photo"
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Browse a library section as a hierarchical tree.

    Examples:
        plexctl shows tree -s "TV Shows"
        plexctl shows tree -s "Anime" --type show
    """
    service = _get_tree_service()
    section_key = require_section_key(service, section)

    items = service.get_section_tree(section_key, media_type=media_type)

    if if_empty_print(items, f"No items found in section '{section}'"):
        return

    if output_csv(_flatten_tree(items), media_tree_item_to_csv, csv_output, output):
        return

    rich_tree = Tree(f"[bold]Section {section}[/bold]")
    _render_nav_tree(rich_tree, items)
    console.print(rich_tree)


@shows_app.command("show")
def shows_show_tree(
    show_key: str = typer.Argument(help="Rating key of the show"),
    depth: int | None = typer.Option(
        None, "--depth", "-d", help="Max tree depth (default: unlimited)"
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Show seasons and episodes for a show as a tree.

    Example:
        plexctl shows show 12345
        plexctl shows show 12345 --depth 1
    """
    service = _get_tree_service()
    show = service.get_show_tree(show_key)

    if show is None:
        console.print(f"[red]Show not found: {show_key}[/red]")
        raise typer.Exit(code=1)

    if csv_output:
        rows = [media_tree_item_to_csv(show)]
        rows.extend(media_tree_item_to_csv(i) for i in _flatten_tree(show.children))
        write_csv_to_output(rows, output)
        return

    rich_tree = Tree(f"[bold]{show.title or show.key}[/bold] [dim](key={show.key})[/dim]")
    _render_nav_tree(rich_tree, show.children, max_depth=depth)
    console.print(rich_tree)


@shows_app.command("season")
def shows_season_tree(
    season_key: str = typer.Argument(help="Rating key of the season"),
    depth: int | None = typer.Option(
        None, "--depth", "-d", help="Max tree depth (default: unlimited)"
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Show episodes in a season as a tree.

    Example:
        plexctl shows season 54321
    """
    service = _get_tree_service()
    season = service.get_season_tree(season_key)

    if season is None:
        console.print(f"[red]Season not found: {season_key}[/red]")
        raise typer.Exit(code=1)

    if csv_output:
        rows = [media_tree_item_to_csv(season)]
        rows.extend(media_tree_item_to_csv(i) for i in _flatten_tree(season.children))
        write_csv_to_output(rows, output)
        return

    parent_label = season.parent_title or "Unknown Show"
    rich_tree = Tree(
        f"[bold]{parent_label} - {season.title or season.key}[/bold]"
        f" [dim](key={season.key})[/dim]"
    )
    _render_nav_tree(rich_tree, season.children, max_depth=depth)
    console.print(rich_tree)
