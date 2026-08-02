"""Item commands - operations on individual media items.

Consolidates item-level operations from across the CLI into a single
domain-oriented command group
"""

from pathlib import Path as FilePath
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from plexctl.client import PlexClient
from plexctl.commands._helpers import (
    media_results_table,
    output_csv,
    print_result,
    require_confirm,
    run_ingest,
)
from plexctl.config import load_config
from plexctl.converters import (
    media_metadata_to_csv,
    search_result_to_csv,
    similar_media_to_csv,
    subtitle_stream_to_csv,
)
from plexctl.models import MediaType, MetadataEdit
from plexctl.options import CsvFlag, OutputFile
from plexctl.services.fixes import FixService
from plexctl.services.metadata import MetadataService
from plexctl.services.search import SearchService
from plexctl.services.server import ServerService

item_app = typer.Typer(
    name="item", help="Operations on individual media items.", no_args_is_help=True
)
console = Console()


def _get_metadata_service() -> MetadataService:
    """Load config and create a connected MetadataService."""
    config = load_config()
    client = PlexClient(config)
    return MetadataService(client)


def _get_server_service() -> ServerService:
    """Load config and create a connected ServerService."""
    config = load_config()
    client = PlexClient(config)
    return ServerService(client)


def _get_fix_service() -> FixService:
    """Load config and create a connected FixService."""
    config = load_config()
    client = PlexClient(config)
    return FixService(client)


def _get_search_service() -> SearchService:
    """Load config and create a connected SearchService."""
    config = load_config()
    client = PlexClient(config)
    return SearchService(client)


# --- Search (from cli.py inline) ------------------------------------------


@item_app.command(name="search", no_args_is_help=True)
def search_items(
    query: str = typer.Argument(help="Search query"),
    section: Annotated[str | None, typer.Option(help="Limit to library section")] = None,
    type: Annotated[MediaType | None, typer.Option(help="Media type filter")] = None,
    csv_output: CsvFlag = False,
    output: OutputFile = None,
    debug: bool = False,
) -> None:
    """Search for media by title."""
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


# --- Edit (from cli.py inline) --------------------------------------------


@item_app.command(name="edit", no_args_is_help=True)
def edit_item(
    key: str = typer.Argument(help="Plex rating key of the item"),
    field: str = typer.Argument(help="Metadata field to edit (e.g. title, summary)"),
    value: str = typer.Argument(help="New value for the field"),
) -> None:
    """Edit a metadata field for a media item.

    Example:
        plexctl item edit 12345 title "New Movie Title"
        plexctl item edit 12345 summary "Updated description"
    """
    service = _get_metadata_service()
    result = service.edit_metadata(key, [MetadataEdit(field=field, value=value)])
    console.print(f"[green]✓ Updated {field} for '{result.title}'[/green]")


# --- Ingest (from cli.py inline) ------------------------------------------


@item_app.command(name="ingest")
def ingest_csv(
    model: str = typer.Argument(
        help="Model to ingest (e.g. triage_issue). Use 'list' to see all."
    ),
    file: str | None = typer.Argument(
        default=None, help="Path to CSV file to ingest. Not needed for 'list'."
    ),
) -> None:
    """Read CSV data back into validated Pydantic models.

    Use 'ingest list' to see available model names.

    Example:
        plexctl item ingest list
        plexctl item ingest triage_issue triage_report.csv
    """
    run_ingest(model, file, command_name="item ingest")


# --- Info (from cli.py inline) --------------------------------------------


@item_app.command(name="info", no_args_is_help=True)
def item_info(
    key: str = typer.Argument(help="Plex rating key of the item"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Show detailed metadata for a media item."""
    service = _get_metadata_service()
    metadata = service.get_metadata(key)

    if metadata is None:
        console.print("[red]Item not found or unsupported type[/red]")
        return

    if output_csv([metadata], media_metadata_to_csv, csv_output, output):
        return

    console.print(f"\n[bold]{metadata.title}[/bold]")
    console.print(f"  Key: {metadata.key}")
    console.print(f"  Type: {metadata.media_type}")
    if metadata.year:
        console.print(f"  Year: {metadata.year}")
    if metadata.rating:
        console.print(f"  Rating: {metadata.rating:.1f}")
    if metadata.audience_rating:
        console.print(f"  Audience Rating: {metadata.audience_rating:.1f}")
    if metadata.content_rating:
        console.print(f"  Content Rating: {metadata.content_rating}")
    if metadata.studio:
        console.print(f"  Studio: {metadata.studio}")
    if metadata.summary:
        console.print(f"\n  {metadata.summary}\n")


# --- Rate (from server.py) ------------------------------------------------


@item_app.command(name="rate")
def rate_item(
    key: str = typer.Argument(help="Plex rating key of the item"),
    rating: float = typer.Argument(help="Rating value (0-10)"),
) -> None:
    """Set the user rating for a media item.

    Example:
        plexctl item rate 12345 8.5
    """
    service = _get_server_service()
    result = service.rate(key, rating)

    print_result(result, f"Set rating for item {result.key} to {rating}", "Failed to set rating")


# --- Watch state (from server.py) -----------------------------------------


@item_app.command(name="watch")
def mark_watched(key: str = typer.Argument(help="Plex rating key of the item")) -> None:
    """Mark a media item as watched.

    Example:
        plexctl item watch 12345
    """
    service = _get_server_service()
    result = service.scrobble(key)

    print_result(result, f"Marked item {result.key} as watched", "Failed to mark as watched")


@item_app.command(name="unwatch")
def mark_unwatched(key: str = typer.Argument(help="Plex rating key of the item")) -> None:
    """Mark a media item as unwatched.

    Example:
        plexctl item unwatch 12345
    """
    service = _get_server_service()
    result = service.unscrobble(key)

    print_result(result, f"Marked item {result.key} as unwatched", "Failed to mark as unwatched")


# --- Delete (from server.py) ----------------------------------------------


@item_app.command(name="delete")
def delete_item(
    key: str = typer.Argument(help="Plex rating key of the item to delete"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a media item from the library.

    This permanently removes the item and its metadata.

    Example:
        plexctl item delete 12345 --yes
    """
    require_confirm(confirm, f"delete item {key}")

    service = _get_server_service()
    result = service.delete_item(key)

    print_result(result, f"Deleted item {result.key}", "Failed to delete")


# --- Matches (from fixes.py) ----------------------------------------------


@item_app.command(name="matches")
def find_matches(
    key: str = typer.Argument(help="Plex rating key of the item"),
    agent: Annotated[
        str | None, typer.Option(help="Metadata agent (e.g. tv.plex.agents.series)")
    ] = None,
    title: Annotated[str | None, typer.Option(help="Override title for the search")] = None,
    year: Annotated[str | None, typer.Option(help="Override year for the search")] = None,
) -> None:
    """Search for metadata matches for an item.

    Shows available matches sorted by score. Use --title and --year
    to override the search terms if the current match is wrong.
    """
    service = _get_fix_service()
    matches = service.find_matches(key, agent=agent, title=title, year=year)

    if not matches:
        console.print("[yellow]No matches found.[/yellow]")
        return

    table = Table(title="Metadata Matches")
    table.add_column("#", style="cyan", justify="right", width=3)
    table.add_column("Score", style="yellow", justify="right")
    table.add_column("Name", style="green")
    table.add_column("Year", style="white", justify="right")
    table.add_column("GUID", style="dim")

    for idx, match in enumerate(matches):
        table.add_row(
            str(idx),
            str(match.score) if match.score is not None else "-",
            match.name,
            match.year or "-",
            match.guid or "-",
        )

    console.print(table)
    console.print("\n[dim]Use 'fix-match' with --match-index to apply a specific match.[/dim]")


# --- Fix match (from fixes.py) --------------------------------------------


@item_app.command(name="fix-match")
def fix_match(
    key: str = typer.Argument(help="Plex rating key of the item"),
    match_index: Annotated[
        int,
        typer.Option(
            "--match-index", help="Which match to apply (0 = best match, see 'matches' command)"
        ),
    ] = 0,
    agent: Annotated[str | None, typer.Option(help="Metadata agent for the search")] = None,
    title: Annotated[str | None, typer.Option(help="Override title for the search")] = None,
    year: Annotated[str | None, typer.Option(help="Override year for the search")] = None,
) -> None:
    """Fix an incorrect metadata match.

    First searches for matches, then applies the best (or specified) one.
    Use the 'matches' command first to see available options.
    """
    service = _get_fix_service()
    result = service.fix_match(key, match_index=match_index, agent=agent, title=title, year=year)

    if result.success:
        matched_to = result.matched_to or ""
        matched_info = f" → '{matched_to}'" if matched_to else ""
        msg = f"[green]✓ Fixed match for '{result.title}' "
        msg += f"(key={result.key}){matched_info}[/green]"
        console.print(msg)
    else:
        console.print(
            f"[red]✗ Failed to fix match for '{result.title}' "
            f"(key={result.key}): {result.error}[/red]"
        )
        raise typer.Exit(1)


# --- Unmatch (from fixes.py) ----------------------------------------------


@item_app.command(name="unmatch")
def unmatch_item(key: str = typer.Argument(help="Plex rating key of the item")) -> None:
    """Remove metadata match from an item.

    This disconnects the item from its current metadata source,
    making it available for rematching with a different source.
    """
    service = _get_fix_service()
    result = service.unmatch(key)

    if result.success:
        console.print(f"[green]✓ Unmatched '{result.title}' (key={result.key})[/green]")
    else:
        console.print(
            f"[red]✗ Failed to unmatch '{result.title}' (key={result.key}): "
            f"{result.error}[/red]"
        )
        raise typer.Exit(1)


# --- Get by key (from search.py) ------------------------------------------


@item_app.command(name="get")
def get_item(
    key: str = typer.Argument(help="Plex rating key to look up"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Find a media item by its Plex rating key.

    Example:
        plexctl item get 12345
    """
    service = _get_search_service()
    result = service.search_by_key(key)

    if result is None:
        console.print(f"[red]No item found with key {key}[/red]")
        raise typer.Exit(code=1)

    if output_csv([result], search_result_to_csv, csv_output, output):
        return

    media_type_str = result.media_type.value if result.media_type else "unknown"
    console.print(f"\n[bold]{result.title}[/bold]")
    console.print(f"  Key:         {result.key}")
    console.print(f"  Type:        {media_type_str}")
    if result.year:
        console.print(f"  Year:        {result.year}")
    if result.rating:
        console.print(f"  Rating:      {result.rating:.1f}")
    if result.section_title:
        console.print(f"  Section:     {result.section_title}")
    if result.summary:
        console.print(f"\n  {result.summary}\n")


# --- Advanced search (from search.py) ---------------------------------------


@item_app.command("advanced")
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
        plexctl item advanced "Inception" --type movie --sort year
        plexctl item advanced "Star Trek" --section 2 --limit 10
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


@item_app.command("actor")
def search_by_actor(
    actor: str = typer.Argument(help="Actor name to search for"),
    type: str = typer.Option("movie", "--type", "-t", help="Media type (movie or show)"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search for media featuring a specific actor.

    Example:
        plexctl item actor "Leonardo DiCaprio"
        plexctl item actor "Bryan Cranston" --type show
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


@item_app.command("director")
def search_by_director(
    director: str = typer.Argument(help="Director name to search for"),
    type: str = typer.Option("movie", "--type", "-t", help="Media type (movie or show)"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search for media directed by a specific director.

    Example:
        plexctl item director "Christopher Nolan"
        plexctl item director "Steven Spielberg" --type movie
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


@item_app.command("genre")
def search_by_genre(
    genre: str = typer.Argument(help="Genre name (e.g. Action, Comedy, Drama)"),
    type: str | None = typer.Option(None, "--type", "-t", help="Media type filter (movie, show)"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search for media by genre.

    Example:
        plexctl item genre Action
        plexctl item genre "Science Fiction" --type movie
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


# --- Search by title (from search.py) ---------------------------------------


@item_app.command("title")
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
    """Search for media by title.

    More targeted than advanced search — uses the library/all endpoint
    with title= filter for exact matches.

    Example:
        plexctl item title "The Matrix"
        plexctl item title "Breaking Bad" --type show --section 2
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


@item_app.command("year")
def search_by_year(
    year: int = typer.Argument(help="Release year to search for"),
    type: str | None = typer.Option(None, "--type", "-t", help="Media type filter (movie, show)"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search for media by release year.

    Example:
        plexctl item year 2024
        plexctl item year 1999 --type movie
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

    for item in results:
        table.add_row(
            item.key,
            item.title or "Unknown",
            item.media_type.value if item.media_type else "-",
            f"{item.rating:.1f}" if item.rating else "-",
        )

    console.print(table)
    console.print(f"[dim]Found {len(results)} results[/dim]")


# --- Find similar (from search.py) ------------------------------------------


@item_app.command("similar")
def find_similar(
    key: str = typer.Argument(help="Plex rating key of the reference item"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Find media similar to a given item.

    Example:
        plexctl item similar 12345
        plexctl item similar 12345 --limit 10
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


@item_app.command("tmdb")
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
        plexctl item tmdb "The Shawshank Redemption"
        plexctl item tmdb "Attack on Titan" --type show --year 2013
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


# --- Tag add/remove commands -----------------------------------------------


def _make_tag_commands(tag_type: str, display_name: str) -> None:
    """Register add-tag and remove-tag CLI commands for a tag type.

    This factory creates two Typer commands on `item_app`:
    - add-<tag_type>: adds one or more tag values
    - remove-<tag_type>: removes one or more tag values

    Args:
        tag_type: Internal tag type identifier (e.g. 'genre', 'collection').
        display_name: Human-readable name for help text and output messages.
    """
    capitalized = display_name.capitalize()
    add_help = f"{capitalized} name(s) to add"
    remove_help = f"{capitalized} name(s) to remove"

    @item_app.command(f"add-{tag_type}")
    def add_tag_cmd(
        key: str = typer.Argument(help="Rating key of the item"),
        values: list[str] = typer.Argument(help=add_help),  # noqa: B008
        locked: bool = typer.Option(
            True, "--locked/--no-locked", help="Lock the field after adding"
        ),
    ) -> None:
        """Add {display_name} tag(s) to a media item.

        Example:
            plexctl item add-{tag_type} 12345 Action
            plexctl item add-{tag_type} 12345 "Sci-Fi" Thriller --no-locked
        """.format(display_name=display_name, tag_type=tag_type)  # noqa: UP032
        service = _get_metadata_service()
        result = service.add_tag(key, tag_type, values, locked=locked)
        if result:
            console.print(f"[green]✓ Added {display_name}(s) to {result.title}[/green]")
        else:
            console.print(f"[red]✗ Failed to add {display_name}(s)[/red]")
            raise typer.Exit(code=1)

    @item_app.command(f"remove-{tag_type}")
    def remove_tag_cmd(
        key: str = typer.Argument(help="Rating key of the item"),
        values: list[str] = typer.Argument(help=remove_help),  # noqa: B008
        locked: bool = typer.Option(
            True, "--locked/--no-locked", help="Lock the field after removing"
        ),
    ) -> None:
        """Remove {display_name} tag(s) from a media item.

        Example:
            plexctl item remove-{tag_type} 12345 Action
            plexctl item remove-{tag_type} 12345 "Sci-Fi" Thriller
        """.format(display_name=display_name, tag_type=tag_type)  # noqa: UP032
        service = _get_metadata_service()
        result = service.remove_tag(key, tag_type, values, locked=locked)
        if result:
            console.print(f"[green]✓ Removed {display_name}(s) from {result.title}[/green]")
        else:
            console.print(f"[red]✗ Failed to remove {display_name}(s)[/red]")
            raise typer.Exit(code=1)


# Register all 8 tag type command pairs.
_make_tag_commands("genre", "genre")
_make_tag_commands("collection", "collection")
_make_tag_commands("label", "label")
_make_tag_commands("director", "director")
_make_tag_commands("writer", "writer")
_make_tag_commands("mood", "mood")
_make_tag_commands("style", "style")
_make_tag_commands("country", "country")


# --- Lock / unlock fields --------------------------------------------------


@item_app.command("lock")
def lock_fields(
    key: str = typer.Argument(help="Rating key of the item"),
    fields: list[str] = typer.Argument(  # noqa: B008
        help="Field name(s) to lock (e.g. title, summary, year)"
    ),
) -> None:
    """Lock metadata field(s) to prevent automatic changes.

    Locked fields are protected from being overwritten during
    Plex metadata refreshes.

    Example:
        plexctl item lock 12345 title summary year
    """
    service = _get_metadata_service()
    result = service.lock_field(key, fields)
    if result:
        console.print(f"[green]✓ Locked field(s) on {result.title}[/green]")
    else:
        console.print("[red]✗ Failed to lock field(s)[/red]")
        raise typer.Exit(code=1)


@item_app.command("unlock")
def unlock_fields(
    key: str = typer.Argument(help="Rating key of the item"),
    fields: list[str] = typer.Argument(  # noqa: B008
        help="Field name(s) to unlock (e.g. title, summary, year)"
    ),
) -> None:
    """Unlock metadata field(s) to allow automatic changes.

    Unlocked fields can be updated by Plex during metadata refreshes.

    Example:
        plexctl item unlock 12345 title summary
    """
    service = _get_metadata_service()
    result = service.unlock_field(key, fields)
    if result:
        console.print(f"[green]✓ Unlocked field(s) on {result.title}[/green]")
    else:
        console.print("[red]✗ Failed to unlock field(s)[/red]")
        raise typer.Exit(code=1)


# --- Subtitle commands ----------------------------------------------------


@item_app.command(name="search-subs")
def search_subtitles(
    key: str = typer.Argument(help="Rating key of the item"),
    language: str = typer.Option("en", "--lang", "-l", help="ISO 639-1 language code"),
    hearing_impaired: int = typer.Option(
        0,
        "--hi",
        help=("Hearing impaired: 0=prefer non-SDH, " "1=prefer SDH, 2=only SDH, 3=only non-SDH"),
    ),
    forced: int = typer.Option(
        0,
        "--forced",
        help=(
            "Forced subtitles: 0=prefer non-forced, "
            "1=prefer forced, 2=only forced, 3=only non-forced"
        ),
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search for available subtitles for a media item.

    Queries the Plex subtitle provider for on-demand subtitles
    matching the specified language and preference filters.

    Example:
        plexctl item search-subs 12345
        plexctl item search-subs 12345 --lang fr --hi 1
    """
    service = _get_metadata_service()
    results = service.search_subtitles(
        key, language=language, hearing_impaired=hearing_impaired, forced=forced
    )

    if not results:
        msg = f"No subtitles found for item {key} (lang={language})"
        console.print(f"[yellow]{msg}[/yellow]")
        return

    if output_csv(results, subtitle_stream_to_csv, csv_output, output):
        return

    table = Table(title=f"Subtitles for item {key}")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Language", style="green")
    table.add_column("Title", style="white")
    table.add_column("Codec", style="yellow")
    table.add_column("Format", style="magenta")
    table.add_column("Forced", style="red")
    table.add_column("HI", style="blue")
    table.add_column("Score", style="green", justify="right")
    table.add_column("Provider", style="dim")

    for sub in results:
        table.add_row(
            str(sub.id),
            sub.language or sub.language_code or "-",
            sub.title or sub.display_title or "-",
            sub.codec or "-",
            sub.format or "-",
            "Yes" if sub.forced else "No",
            "Yes" if sub.hearing_impaired else "No",
            str(sub.score) if sub.score is not None else "-",
            sub.provider or "-",
        )

    console.print(table)
    console.print(f"[dim]Found {len(results)} subtitle(s)[/dim]")


@item_app.command(name="download-sub")
def download_subtitle(
    key: str = typer.Argument(help="Rating key of the item"),
    stream_id: int = typer.Argument(help="ID of the subtitle stream to download"),
) -> None:
    """Download (apply) a subtitle to a media item.

    Use 'search-subs' first to find available subtitle stream IDs.
    The subtitle will be applied asynchronously by the Plex server.

    Example:
        plexctl item download-sub 12345 5432
    """
    service = _get_metadata_service()
    try:
        service.download_subtitle(key, stream_id)
    except ValueError as exc:
        console.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(code=1) from None

    msg = f"[green]✓ Subtitle download requested for " f"stream {stream_id} on item {key}[/green]"
    console.print(msg)


@item_app.command(name="upload-sub")
def upload_subtitle(
    key: str = typer.Argument(help="Rating key of the item"),
    filepath: str = typer.Argument(help="Path to subtitle file (.srt, .ass, etc.)"),
) -> None:
    """Upload a subtitle file for a media item.

    The file must be a supported subtitle format (.srt, .ass, .ssa, etc.)
    and must exist on the local filesystem.

    Example:
        plexctl item upload-sub 12345 /path/to/subtitle.srt
    """
    sub_path = FilePath(filepath)
    if not sub_path.exists():
        console.print(f"[red]✗ File not found: {filepath}[/red]")
        raise typer.Exit(code=1)

    if not sub_path.is_file():
        console.print(f"[red]✗ Not a file: {filepath}[/red]")
        raise typer.Exit(code=1)

    service = _get_metadata_service()
    service.upload_subtitle(key, filepath)
    console.print(f"[green]✓ Uploaded subtitle '{sub_path.name}' to item {key}[/green]")


@item_app.command(name="remove-sub")
def remove_subtitle(
    key: str = typer.Argument(help="Rating key of the item"),
    stream_id: int | None = typer.Option(
        None, "--id", help="ID of the subtitle stream to remove"
    ),
    stream_title: str | None = typer.Option(
        None, "--title", help="Title of the subtitle stream to remove"
    ),
) -> None:
    """Remove a subtitle from a media item.

    Provide either --id or --title to identify which subtitle to remove.
    Embedded subtitles cannot be removed.

    Example:
        plexctl item remove-sub 12345 --id 5432
        plexctl item remove-sub 12345 --title "English (SRT)"
    """
    if stream_id is None and stream_title is None:
        console.print("[red]✗ Either --id or --title must be provided[/red]")
        raise typer.Exit(code=1)

    service = _get_metadata_service()
    try:
        service.remove_subtitle(key, stream_id=stream_id, stream_title=stream_title)
    except ValueError as exc:
        console.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(code=1) from None

    identifier = f"--id {stream_id}" if stream_id else f"--title '{stream_title}'"
    console.print(f"[green]✓ Removed subtitle ({identifier}) from item {key}[/green]")


@item_app.command(name="set-progress")
def set_item_progress(
    rating_key: str = typer.Argument(help="Plex rating key of the item."),
    time_ms: int = typer.Argument(help="Progress time in milliseconds."),
    state: str = typer.Option(
        "stopped", "--state", help="Playback state to set (default: stopped)."
    ),
) -> None:
    """Set playback progress for a media item.

    Time is specified in milliseconds. Use this to mark how far you've
    watched an item.

    Example:
        plexctl item set-progress 12345 3600000
        plexctl item set-progress 12345 1800000 --state paused
    """
    service = _get_server_service()
    result = service.set_progress(rating_key, time_ms, state)

    print_result(
        result,
        f"Set progress for item {result.key} to {time_ms}ms ({state})",
        "Failed to set progress",
    )


@item_app.command(name="merge")
def merge_items(
    target: str = typer.Argument(help="Rating key of the target item"),
    sources: list[str] = typer.Argument(  # noqa: B008
        ..., help="Rating keys of items to merge into target"
    ),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Merge multiple media items into one.

    The target item absorbs all source items. Source items are removed.

    Example:
        plexctl item merge 12345 67890 54321 --yes
    """
    require_confirm(confirm, f"merge {len(sources)} item(s) into {target}")

    service = _get_server_service()
    try:
        result = service.merge(target, list(sources))
    except ValueError as exc:
        console.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(code=1) from None

    print_result(result, f"Merged {len(sources)} item(s) into {result.key}", "Failed to merge")
