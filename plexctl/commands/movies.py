"""Movie browsing commands for plexctl.

Provides commands for listing and exploring movies:
- List all movies in a section (default)
- Tree view with --tree flag, showing rating keys

Examples:
    plexctl movies                      # List movies in default section
    plexctl movies --tree               # Tree view with (key) labels
    plexctl movies --section "Anime Films"  # Specify a different section
"""

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from plexctl.client import PlexClient
from plexctl.config import load_config
from plexctl.converters import media_metadata_to_csv, media_tree_item_to_csv
from plexctl.csv_utils import write_csv_to_output
from plexctl.models import MediaTreeItem
from plexctl.options import CsvFlag, OutputFile
from plexctl.services.metadata import MetadataService
from plexctl.services.tree import TreeService

movies_app = typer.Typer(
    name="movies",
    help="Browse movies in your library.",
    invoke_without_command=True,
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


def _render_movie_tree(items: list[MediaTreeItem]) -> Tree:
    """Render movies as a rich Tree with (key) labels."""
    tree = Tree("[bold]Movies[/bold]")
    for item in items:
        year_label = f" [dim]({item.year})[/dim]" if item.year else ""
        label = f"{item.title or item.key}{year_label} [dim](key={item.key})[/dim]"
        tree.add(label)
    return tree


@movies_app.callback(invoke_without_command=True)
def movies_default(
    ctx: typer.Context,
    section: str = typer.Option(
        "Movies",
        "--section",
        "-s",
        help="Library section name",
    ),
    limit: int = typer.Option(
        25,
        "--limit",
        "-l",
        help="Maximum number of results (list view only)",
    ),
    tree: bool = typer.Option(
        False,
        "--tree",
        "-t",
        help="Display as a tree with rating keys",
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Browse movies in your library.

    Examples:
        plexctl movies                      # List movies in default section
        plexctl movies --tree               # Tree view with (key) labels
        plexctl movies --section "Anime Films"
    """
    # If a subcommand was specified, let it handle things
    if ctx.invoked_subcommand is not None:
        return

    service = _get_metadata_service()
    all_movies = service.get_all_movies(section)

    if not all_movies:
        console.print(f"[dim]No movies found in section '{section}'[/dim]")
        return

    if tree:
        tree_service = _get_tree_service()
        section_key = tree_service.resolve_section_key(section)
        if section_key is None:
            console.print(f"[red]Section not found: {section}[/red]")
            console.print(
                "[dim]Use 'plexctl library list' to see available sections.[/dim]"
            )
            raise typer.Exit(code=1)

        items = tree_service.get_section_tree(section_key, media_type="movie")
        if not items:
            console.print(f"[dim]No movies found in section '{section}'[/dim]")
            return

        if csv_output:
            rows = [media_tree_item_to_csv(i) for i in items]
            write_csv_to_output(rows, output)
            return

        rich_tree = _render_movie_tree(items)
        console.print(rich_tree)
        return

    if csv_output:
        rows = [media_metadata_to_csv(m) for m in all_movies[:limit]]
        write_csv_to_output(rows, output)
        return

    table = Table(title=f"Movies in {section}")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Year", style="yellow", justify="right")
    table.add_column("Rating", style="magenta", justify="right")

    for movie in all_movies[:limit]:
        table.add_row(
            movie.key,
            movie.title or "Unknown",
            str(movie.year) if movie.year else "-",
            f"{movie.audience_rating:.1f}" if movie.audience_rating else "-",
        )

    console.print(table)
    if len(all_movies) > limit:
        console.print(
            f"[dim]Showing {limit} of {len(all_movies)} movies. "
            f"Use --limit to see more.[/dim]"
        )
