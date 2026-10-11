"""Search commands for plexctl.

Consolidates the media-search family that used to live under `item`:
- Title search (metadata search across sections)
- Advanced search (hub search with filters)
- Filtered searches: actor, director, genre, title, year
- Similar items
- TMDB-integrated search
"""

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from plexctl.client import PlexClient
from plexctl.commands._helpers import media_results_table, output_csv
from plexctl.config import load_config
from plexctl.converters import (
    media_metadata_to_csv,
    search_result_to_csv,
    similar_media_to_csv,
)
from plexctl.models import MediaType
from plexctl.options import CsvFlag, OutputFile
from plexctl.services.metadata import MetadataService
from plexctl.services.search import SearchService
from plexctl.utils.live import stream_table

search_app = typer.Typer(
    name="search",
    help="Search Plex for media by title, people, genre, year, and more.",
    no_args_is_help=True,
)
console = Console()


def _get_metadata_service() -> MetadataService:
    """Load config and create a connected MetadataService."""
    config = load_config()
    client = PlexClient(config)
    return MetadataService(client)


def _get_search_service() -> SearchService:
    """Load config and create a connected SearchService."""
    config = load_config()
    client = PlexClient(config)
    return SearchService(client)


def _run_media_search(
    query: str,
    section: str | None = None,
    type: MediaType | None = None,
    csv_output: bool = False,
    output: OutputFile = None,
) -> None:
    """Run a media title search and display results."""
    service = _get_metadata_service()
    results = service.search(query, section_title=section, media_type=type)

    if not results:
        console.print(f"[yellow]No results found for '{query}'[/yellow]")
        return

    if output_csv(results, media_metadata_to_csv, csv_output, output):
        return

    table = media_results_table(f"Search: {query}", results)
    console.print(table)
    console.print(f"[dim]Found {len(results)} results[/dim]")


@search_app.callback(invoke_without_command=True)
def search_default(ctx: typer.Context) -> None:
    """Search Plex for media by title.

    Use 'plexctl search media QUERY' to run a title search:

        plexctl search media "One Piece"
    """
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


# --- Title search (from cli.py inline) -------------------------------------


@search_app.command(name="media", no_args_is_help=True)
def search_media(
    query: str = typer.Argument(help="Search query"),
    section: Annotated[str | None, typer.Option(help="Limit to library section")] = None,
    type: Annotated[MediaType | None, typer.Option(help="Media type filter")] = None,
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search for media by title."""
    _run_media_search(query, section=section, type=type, csv_output=csv_output, output=output)


# --- Advanced search (from search.py) ---------------------------------------


@search_app.command("advanced")
def search_advanced(
    query: str = typer.Argument(help="Search query"),
    type: str | None = typer.Option(
        None, "--type", "-t", help="Media type filter (movie, show, episode, etc.)"
    ),
    section: str | None = typer.Option(
        None, "--section", "-s", help="Section key to limit search"
    ),
    sort: str | None = typer.Option(
        None, "--sort", help="Sort order (added, title, year, rating)"
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Advanced search with multiple filters.

    Uses Plex Hub search for comprehensive results across all sections.

    Example:
        plexctl search advanced "Inception" --type movie --sort year
        plexctl search advanced "Star Trek" --section 2 --limit 10
    """
    service = _get_search_service()
    results = service.search_advanced(
        query=query, media_type=type, section=section, sort=sort, limit=limit
    )

    if not results:
        console.print(f"[yellow]No results found for '{query}'[/yellow]")
        return

    if output_csv(results, search_result_to_csv, csv_output, output):
        return

    table = media_results_table(
        f"Advanced Search: {query}",
        results,
        extra_header="Rating",
        extra_accessor=lambda i: f"{i.rating:.1f}" if i.rating else "-",
    )
    console.print(table)
    console.print(f"[dim]Found {len(results)} results[/dim]")


@search_app.command("actor")
def search_by_actor(
    actor: str = typer.Argument(help="Actor name to search for"),
    type: str = typer.Option("movie", "--type", "-t", help="Media type (movie or show)"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search for media featuring a specific actor.

    Example:
        plexctl search actor "Leonardo DiCaprio"
        plexctl search actor "Bryan Cranston" --type show
    """
    service = _get_search_service()
    results = service.search_by_actor(actor, media_type=type)

    if not results:
        console.print(f"[yellow]No results found for actor '{actor}'[/yellow]")
        return

    if output_csv(results, search_result_to_csv, csv_output, output):
        return

    table = media_results_table(f"Actor: {actor}", results)
    console.print(table)
    console.print(f"[dim]Found {len(results)} results[/dim]")


# --- Search by director (from search.py) ------------------------------------


@search_app.command("director")
def search_by_director(
    director: str = typer.Argument(help="Director name to search for"),
    type: str = typer.Option("movie", "--type", "-t", help="Media type (movie or show)"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search for media directed by a specific director.

    Example:
        plexctl search director "Christopher Nolan"
        plexctl search director "Steven Spielberg" --type movie
    """
    service = _get_search_service()
    results = service.search_by_director(director, media_type=type)

    if not results:
        console.print(f"[yellow]No results found for director '{director}'[/yellow]")
        return

    if output_csv(results, search_result_to_csv, csv_output, output):
        return

    table = media_results_table(f"Director: {director}", results)
    console.print(table)
    console.print(f"[dim]Found {len(results)} results[/dim]")


# --- Search by genre (from search.py) ---------------------------------------


@search_app.command("genre")
def search_by_genre(
    genre: str = typer.Argument(help="Genre name (e.g. Action, Comedy, Drama)"),
    type: str | None = typer.Option(None, "--type", "-t", help="Media type filter (movie, show)"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search for media by genre.

    Example:
        plexctl search genre Action
        plexctl search genre "Science Fiction" --type movie
    """
    service = _get_search_service()
    results = service.search_by_genre(genre, media_type=type)

    if not results:
        console.print(f"[yellow]No results found for genre '{genre}'[/yellow]")
        return

    if output_csv(results, search_result_to_csv, csv_output, output):
        return

    table = media_results_table(f"Genre: {genre}", results)
    console.print(table)
    console.print(f"[dim]Found {len(results)} results[/dim]")


# --- Search by title filter (from search.py) ---------------------------------


@search_app.command("title")
def search_by_title(
    query: str = typer.Argument(help="Title to search for"),
    type: str | None = typer.Option(
        None, "--type", "-t", help="Media type filter (movie, show, etc.)"
    ),
    section: str | None = typer.Option(
        None, "--section", "-s", help="Section key to limit search"
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search for media by title filter.

    More targeted than advanced search — uses the library/all endpoint
    with title= filter for exact matches.

    Example:
        plexctl search title "The Matrix"
        plexctl search title "Breaking Bad" --type show --section 2
    """
    service = _get_search_service()
    results = service.search_by_title(query, media_type=type, section=section)

    if not results:
        console.print(f"[yellow]No results found for '{query}'[/yellow]")
        return

    if output_csv(results, search_result_to_csv, csv_output, output):
        return

    table = media_results_table(f"Title Search: {query}", results)
    console.print(table)
    console.print(f"[dim]Found {len(results)} results[/dim]")


# --- Search by year (from search.py) ----------------------------------------


@search_app.command("year")
def search_by_year(
    year: int = typer.Argument(help="Release year to search for"),
    type: str | None = typer.Option(None, "--type", "-t", help="Media type filter (movie, show)"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search for media by release year.

    Example:
        plexctl search year 2024
        plexctl search year 1999 --type movie
    """
    service = _get_search_service()
    results = service.search_by_year(year, media_type=type)

    if not results:
        console.print(f"[yellow]No results found for year {year}[/yellow]")
        return

    if output_csv(results, search_result_to_csv, csv_output, output):
        return

    table = Table(title=f"Year: {year}")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Rating", style="blue", justify="right")

    with stream_table(table, console):
        for item in results:
            table.add_row(
                item.key,
                item.title or "Unknown",
                item.media_type.value if item.media_type else "-",
                f"{item.rating:.1f}" if item.rating else "-",
            )
    console.print(f"[dim]Found {len(results)} results[/dim]")


# --- Find similar (from search.py) ------------------------------------------


@search_app.command("similar")
def find_similar(
    key: str = typer.Argument(help="Plex rating key of the reference item"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Find media similar to a given item.

    Example:
        plexctl search similar 12345
        plexctl search similar 12345 --limit 10
    """
    service = _get_search_service()
    similar = service.find_similar(key, limit=limit)

    if not similar:
        console.print(f"[yellow]No similar items found for key {key}[/yellow]")
        return

    if output_csv(similar, similar_media_to_csv, csv_output, output):
        return

    table = media_results_table(
        f"Similar to {key}",
        similar,
        extra_header="Match %",
        extra_accessor=lambda i: f"{i.similarity}%" if i.similarity is not None else "-",
    )
    console.print(table)
    console.print(f"[dim]Found {len(similar)} similar items[/dim]")


# --- TMDB search (from search.py) ------------------------------------------


@search_app.command("tmdb")
def search_tmdb(
    query: str = typer.Argument(help="Search query"),
    type: str = typer.Option("movie", "--type", "-t", help="Media type (movie or show)"),
    year: int | None = typer.Option(None, "--year", "-y", help="Release year"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search for media using TMDB-integrated search.

    Uses Plex Hub search which cross-references with TMDB metadata.
    Useful for finding items when you know the TMDB title.

    Example:
        plexctl search tmdb "The Shawshank Redemption"
        plexctl search tmdb "Attack on Titan" --type show --year 2013
    """
    service = _get_search_service()
    results = service.search_tmdb(query, media_type=type, year=year)

    if not results:
        console.print(f"[yellow]No TMDB results found for '{query}'[/yellow]")
        return

    if output_csv(results, search_result_to_csv, csv_output, output):
        return

    table = media_results_table(
        f"TMDB Search: {query}",
        results,
        extra_header="Section",
        extra_accessor=lambda i: i.section_title or "-",
    )
    console.print(table)
    console.print(f"[dim]Found {len(results)} results[/dim]")
