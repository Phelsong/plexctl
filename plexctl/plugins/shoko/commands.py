"""Typer CLI commands for querying Shoko Server.

Provides subcommands for listing series, episodes, and files from
the Shoko metadata server, helping triage file parsing issues
between Shoko and Plex.
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.live import Live
from rich.table import Table

from plexctl.commands._helpers import output_csv
from plexctl.models import PlexMatchBatchResult, PlexMatchResult, ShokoSeries
from plexctl.options import CsvFlag, OutputFile
from plexctl.plugins.shoko.converters import (
    crc_audit_to_csv,
    shoko_episode_to_csv,
    shoko_file_to_csv,
    shoko_mismatch_to_csv,
    shoko_series_to_csv,
    tmdb_search_result_to_csv,
)
from plexctl.plugins.shoko.service import ShokoService

shoko_app = typer.Typer(
    name="shoko",
    help="Query Shoko Server for anime metadata and file information.",
    no_args_is_help=True,
)
console = Console()


def _get_service() -> ShokoService:
    """Load config and create a connected ShokoService."""
    from plexctl.plugins.shoko.client import ShokoClient
    from plexctl.plugins.shoko.config import load_shoko_config

    config = load_shoko_config()
    client = ShokoClient(config)
    return ShokoService(client)


def _format_episode_type(ep_type: str) -> str:
    """Format episode type for display."""
    type_labels = {
        "episode": "E",
        "special": "S",
        "credit": "C",
        "trailer": "T",
        "parody": "P",
        "other": "O",
        "unknown": "?",
    }
    return type_labels.get(ep_type, "?")


@shoko_app.command()
def series(
    search: Annotated[str | None, typer.Option(help="Search series by name")] = None,
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List or search series from Shoko Server.

    Paginates through all series and streams rows into a live table.
    Use --search to filter by name.
    """
    service = _get_service()

    if csv_output:
        # For CSV, collect all pages then dump
        all_series: list[ShokoSeries] = []
        if search:
            all_series = service.search_series(search)
        else:
            page = 1
            total = None
            while total is None or len(all_series) < total:
                batch, total = service.list_series(page=page, page_size=100)
                if not batch:
                    break
                all_series.extend(batch)
                page += 1
        if output_csv(all_series, shoko_series_to_csv, csv_output, output):
            return

    # Build live table
    table = Table(title="Shoko Series")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Name", style="green")
    table.add_column("AniDB", style="yellow", justify="right")
    table.add_column("Episodes", style="magenta", justify="right")
    table.add_column("TMDB", style="blue")

    if search:
        results = service.search_series(search)
        total = len(results)
        for s in results:
            _add_series_row(table, s)
        table.title = f"Shoko Series ({total} found)"
        console.print(table)
        return

    # Paginate with live updates
    page_size = 100
    with Live(table, console=console, refresh_per_second=10):
        page = 1
        total = None
        fetched = 0
        while total is None or fetched < total:
            batch, total = service.list_series(page=page, page_size=page_size)
            if not batch:
                break
            for s in batch:
                _add_series_row(table, s)
            fetched += len(batch)
            table.title = f"Shoko Series ({fetched}/{total})"
            page += 1
            if page > (total // page_size) + 2:
                break


def _add_series_row(table: Table, s: ShokoSeries) -> None:
    """Add a single series row to a Rich table."""
    tmdb_info = []
    if s.ids.tmdb_show:
        tmdb_info.append(f"Show({len(s.ids.tmdb_show)})")
    if s.ids.tmdb_movie:
        tmdb_info.append(f"Movie({len(s.ids.tmdb_movie)})")
    tmdb_str = ", ".join(tmdb_info) if tmdb_info else "[dim]none[/dim]"

    table.add_row(
        str(s.ids.id),
        s.name or "Unknown",
        str(s.ids.anidb or "-"),
        str(s.local_sizes.episodes + s.local_sizes.specials),
        tmdb_str,
    )


@shoko_app.command()
def episodes(
    series_id: Annotated[int, typer.Argument(help="Shoko series ID")],
    page: Annotated[int, typer.Option(help="Page number (1-indexed)")] = 1,
    limit: Annotated[int, typer.Option(help="Results per page")] = 50,
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List episodes for a series from Shoko Server."""
    service = _get_service()
    results, total = service.list_episodes(series_id, page=page, page_size=limit)

    if not results:
        console.print(f"[yellow]No episodes found for series {series_id}[/yellow]")
        return

    if output_csv(results, shoko_episode_to_csv, csv_output, output):
        return

    table = Table(title=f"Episodes for Series {series_id} ({total} total)")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Type", style="yellow", justify="center")
    table.add_column("Ep#", style="magenta", justify="right")
    table.add_column("Season", style="blue", justify="right")
    table.add_column("Name", style="green")
    table.add_column("Hidden", style="dim")

    for ep in results:
        type_label = _format_episode_type(ep.episode_type.value)
        table.add_row(
            str(ep.id),
            type_label,
            str(ep.episode_number or "-"),
            str(ep.season_number if ep.season_number is not None else "-"),
            ep.name or "[dim]Unknown[/dim]",
            "yes" if ep.is_hidden else "",
        )

    console.print(table)


@shoko_app.command()
def files(
    search: Annotated[str | None, typer.Option(help="Search files by path suffix")] = None,
    page: Annotated[int, typer.Option(help="Page number (1-indexed)")] = 1,
    limit: Annotated[int, typer.Option(help="Results per page")] = 25,
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List or search files from Shoko Server."""
    service = _get_service()

    if search:
        results = service.search_file_by_path(search)
        total = len(results)
    else:
        results, total = service.list_files(page=page, page_size=limit)

    if not results:
        console.print("[yellow]No files found[/yellow]")
        return

    if output_csv(results[:limit], shoko_file_to_csv, csv_output, output):
        return

    table = Table(title=f"Shoko Files ({total} total)")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Filename", style="green", max_width=50)
    table.add_column("Series", style="yellow")
    table.add_column("Res", style="magenta", justify="right")
    table.add_column("Var", style="dim")
    table.add_column("Ign", style="dim")

    for f in results[:limit]:
        table.add_row(
            str(f.id),
            f.filename or "[dim]unknown[/dim]",
            f.series_name or "[dim]unlinked[/dim]",
            f.resolution or "-",
            "V" if f.is_variation else "",
            "I" if f.is_ignored else "",
        )

    console.print(table)

    if not search and total > limit:
        console.print(f"[dim]Showing page {page}. Use --page to see more results.[/dim]")


@shoko_app.command()
def unlinked(csv_output: CsvFlag = False, output: OutputFile = None) -> None:
    """Find files that are not linked to any series in Shoko."""
    service = _get_service()

    console.print("[bold]Scanning for unlinked files...[/bold]")
    results = service.find_unlinked_files()

    if not results:
        console.print("[green]All files are properly linked to series.[/green]")
        return

    if output_csv(results, shoko_file_to_csv, csv_output, output):
        return

    table = Table(title=f"Unlinked Files ({len(results)} found)")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Filename", style="green", max_width=60)
    table.add_column("Path", style="yellow", max_width=80)
    table.add_column("Accessible", style="magenta")

    for f in results:
        table.add_row(
            str(f.id),
            f.filename or "[dim]unknown[/dim]",
            f.relative_path or "-",
            "yes" if f.is_accessible else "[red]no[/red]",
        )

    console.print(table)


@shoko_app.command()
def problems(csv_output: CsvFlag = False, output: OutputFile = None) -> None:
    """Find series with potential problems in Shoko data."""
    service = _get_service()

    console.print("[bold]Scanning for problem series...[/bold]")
    results = service.find_problem_series()

    if not results:
        console.print("[green]No problems found in Shoko data.[/green]")
        return

    if output_csv(results, shoko_mismatch_to_csv, csv_output, output):
        return

    table = Table(title=f"Shoko Problem Series ({len(results)} found)")
    table.add_column("Type", style="yellow")
    table.add_column("Severity", style="magenta")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Name", style="green")
    table.add_column("Detail", style="white", max_width=60)

    severity_colors = {"error": "red", "warning": "yellow", "info": "blue"}

    for m in results:
        color = severity_colors.get(m.severity, "white")
        table.add_row(
            m.mismatch_type,
            f"[{color}]{m.severity}[/{color}]",
            str(m.shoko_id or "-"),
            m.name or "[dim]unknown[/dim]",
            m.detail,
        )

    console.print(table)


@shoko_app.command("search-tmdb")
def search_tmdb(
    query: Annotated[str, typer.Argument(help="Search query for TMDB shows")],
    year: Annotated[int | None, typer.Option(help="Filter by first aired year")] = None,
    movies: Annotated[
        bool, typer.Option("--movies", help="Search TMDB movies instead of shows")
    ] = False,
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Search TMDB for shows/movies to link to Shoko series."""
    service = _get_service()

    if movies:
        results = service.search_tmdb_movies(query, year=year)
        label = "Movies"
    else:
        results = service.search_tmdb_shows(query, year=year)
        label = "Shows"

    if not results:
        console.print(f"[yellow]No TMDB {label.lower()} found for '{query}'[/yellow]")
        return

    if output_csv(results, tmdb_search_result_to_csv, csv_output, output):
        return

    table = Table(title=f"TMDB {label} Search: '{query}' ({len(results)} results)")
    table.add_column("TMDB ID", style="cyan", justify="right")
    table.add_column("Name", style="green")
    table.add_column("Year", style="yellow", justify="right")
    table.add_column("Overview", style="white", max_width=60)

    for r in results:
        table.add_row(
            str(r.id),
            r.name,
            str(r.year or "-"),
            (
                (r.overview or "")[:60] + "..."
                if r.overview and len(r.overview) > 60
                else r.overview or ""
            ),
        )

    console.print(table)
    console.print("[dim]Use 'link-tmdb' to link a TMDB result to a Shoko series.[/dim]")


@shoko_app.command("link-tmdb")
def link_tmdb(
    series_id: Annotated[int, typer.Argument(help="Shoko series ID to link")],
    tmdb_id: Annotated[int, typer.Argument(help="TMDB show/movie ID to link")],
    replace: Annotated[
        bool, typer.Option(help="Replace all existing TMDB links with this one")
    ] = False,
    refresh: Annotated[bool, typer.Option(help="Force refresh metadata after linking")] = True,
    movie: Annotated[
        bool, typer.Option("--movie", help="Link TMDB movie instead of show")
    ] = False,
    episode_id: Annotated[
        int | None, typer.Option(help="AniDB episode ID (required for movie links)")
    ] = None,
) -> None:
    """Link a TMDB show/movie to a Shoko series."""
    service = _get_service()

    # Verify the series exists first
    try:
        series_data = service.get_series(series_id)
    except Exception as exc:
        console.print(f"[red]Error: Could not find series {series_id}: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if movie:
        if episode_id is None:
            # Auto-detect AniDB episode ID for single-episode series
            episodes, total = service.list_episodes(series_id, page_size=1)
            if total == 1 and episodes and episodes[0].anidb_id:
                episode_id = episodes[0].anidb_id
                console.print(f"[dim]Auto-detected AniDB episode ID: {episode_id}[/dim]")
            else:
                console.print(
                    "[red]Movie links require --episode-id (AniDB episode ID). "
                    f"Series has {total} episode(s).[/red]"
                )
                raise typer.Exit(code=1)

        console.print(
            f"[bold]Linking TMDB movie {tmdb_id} to "
            f"'{series_data.name}' (ID: {series_id}, "
            f"AniDB episode: {episode_id})[/bold]"
        )
        result = service.link_tmdb_movie(
            series_id, tmdb_id, episode_id, replace=replace, refresh=refresh
        )
    else:
        console.print(
            f"[bold]Linking TMDB show {tmdb_id} to "
            f"'{series_data.name}' (ID: {series_id})[/bold]"
        )
        result = service.link_tmdb_show(series_id, tmdb_id, replace=replace, refresh=refresh)

    if result.success:
        link_type = "movie" if movie else "show"
        console.print(
            f"[green]Successfully linked TMDB {link_type} {tmdb_id} "
            f"to series '{series_data.name}' (ID: {series_id})[/green]"
        )
        if refresh:
            console.print("[dim]Metadata refresh scheduled.[/dim]")
    else:
        console.print(f"[red]Failed to link: {result.error}[/red]")
        raise typer.Exit(code=1)


@shoko_app.command("unlink-tmdb")
def unlink_tmdb(
    series_id: Annotated[int, typer.Argument(help="Shoko series ID to unlink")],
    tmdb_id: Annotated[int, typer.Argument(help="TMDB show ID to remove")],
    purge: Annotated[bool, typer.Option(help="Purge cached metadata for the link")] = False,
) -> None:
    """Remove a TMDB show link from a Shoko series."""
    service = _get_service()

    # Verify the series exists
    try:
        series_data = service.get_series(series_id)
        console.print(
            f"[bold]Removing TMDB show {tmdb_id} from "
            f"'{series_data.name}' (ID: {series_id})[/bold]"
        )
    except Exception as exc:
        console.print(f"[red]Error: Could not find series {series_id}: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    result = service.unlink_tmdb_show(series_id, tmdb_id, purge=purge)

    if result.success:
        console.print(
            f"[green]Successfully unlinked TMDB show {tmdb_id} "
            f"from series '{series_data.name}' (ID: {series_id})[/green]"
        )
        if purge:
            console.print("[dim]Cached metadata will be purged.[/dim]")
    else:
        console.print(f"[red]Failed to unlink: {result.error}[/red]")
        raise typer.Exit(code=1)


@shoko_app.command("refresh-tmdb")
def refresh_tmdb(
    series_id: Annotated[
        int, typer.Argument(help="Shoko series ID to refresh TMDB metadata for")
    ],
) -> None:
    """Refresh TMDB show metadata for a Shoko series."""
    service = _get_service()

    # Verify the series exists
    try:
        series_data = service.get_series(series_id)
        tmdb_links = series_data.ids.tmdb_show
        if not tmdb_links:
            console.print(
                f"[yellow]Series '{series_data.name}' (ID: {series_id}) has no "
                f"TMDB show links. Link one first with 'link-tmdb'.[/yellow]"
            )
            raise typer.Exit()
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error: Could not find series {series_id}: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[bold]Refreshing TMDB metadata for '{series_data.name}' "
        f"(ID: {series_id}, {len(tmdb_links)} link(s))[/bold]"
    )

    result = service.refresh_tmdb_show(series_id)

    if result.success:
        console.print(
            f"[green]TMDB metadata refresh completed for "
            f"'{series_data.name}' (ID: {series_id})[/green]"
        )
    else:
        console.print(f"[red]Failed to refresh: {result.error}[/red]")
        raise typer.Exit(code=1)


@shoko_app.command("crc-audit")
def crc_audit(csv_output: CsvFlag = False, output: OutputFile = None) -> None:
    """Audit all Shoko files for CRC hash completeness.

    Checks each file's filename for real CRC32 hashes vs %CRC placeholders.
    Files with %CRC haven't been hashed by Shoko yet, which can cause
    issues with the ShokoRelay scanner matching files to episodes.
    """
    service = _get_service()

    console.print("[bold]Auditing CRC hashes across all Shoko files...[/bold]")
    _, report = service.audit_crc_hashes()

    if output_csv(report.series_missing_crc, crc_audit_to_csv, csv_output, output):
        return

    # Print summary
    console.print(
        f"\n[bold]CRC Hash Audit Summary[/bold]\n"
        f"  Total series:  {report.total_series}\n"
        f"  Total files:   {report.total_files}\n"
        f"  [green]With CRC:      {report.files_with_crc}[/green]\n"
        f"  [red]Missing CRC:   {report.files_missing_crc}[/red]\n"
        f"  [yellow]No bracket:   {report.files_no_bracket}[/yellow]\n"
    )

    if not report.series_missing_crc:
        console.print("[green]All files have real CRC32 hashes![/green]")
        return

    console.print(
        f"[bold red]{len(report.series_missing_crc)} series have files "
        f"missing CRC hashes:[/bold red]\n"
    )

    table = Table(title="Series Missing CRC Hashes")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Name", style="green")
    table.add_column("Total", style="white", justify="right")
    table.add_column("Has CRC", style="green", justify="right")
    table.add_column("[red]Missing[/red]", style="red", justify="right")
    table.add_column("No Bracket", style="yellow", justify="right")
    table.add_column("Sample Paths", style="dim", max_width=60)

    for r in report.series_missing_crc[:25]:
        paths_str = "\n".join(r.missing_crc_paths[:3]) if r.missing_crc_paths else ""
        table.add_row(
            str(r.series_id),
            r.series_name,
            str(r.total_files),
            str(r.files_with_crc),
            str(r.files_missing_crc),
            str(r.files_no_bracket),
            paths_str,
        )

    console.print(table)

    if len(report.series_missing_crc) > 25:
        console.print(
            f"[dim]Showing top 25 of {len(report.series_missing_crc)} series. "
            f"Use --csv for full output.[/dim]"
        )

    console.print(
        "\n[dim]Tip: Use 'shoko rehash <file_id>' to trigger CRC hashing for "
        "individual files, or 'shoko trigger-import' to rescan all files.[/dim]"
    )


@shoko_app.command("rehash")
def rehash_file(file_id: Annotated[int, typer.Argument(help="Shoko file ID to rehash")]) -> None:
    """Trigger a CRC rehash for a single file in Shoko."""
    service = _get_service()

    console.print(f"[bold]Triggering rehash for file {file_id}...[/bold]")
    success = service.rehash_file(file_id)

    if success:
        console.print(f"[green]Rehash triggered for file {file_id}[/green]")
    else:
        console.print(f"[red]Failed to trigger rehash for file {file_id}[/red]")
        raise typer.Exit(code=1)


@shoko_app.command("rescan")
def rescan_file(
    file_id: Annotated[int, typer.Argument(help="Shoko file ID to rescan on AniDB")],
) -> None:
    """Trigger an AniDB rescan for a single file in Shoko."""
    service = _get_service()

    console.print(f"[bold]Triggering rescan for file {file_id}...[/bold]")
    success = service.rescan_file(file_id)

    if success:
        console.print(f"[green]Rescan triggered for file {file_id}[/green]")
    else:
        console.print(f"[red]Failed to trigger rescan for file {file_id}[/red]")
        raise typer.Exit(code=1)


@shoko_app.command("trigger-import")
def trigger_import() -> None:
    """Trigger Shoko to import new files from disk."""
    service = _get_service()

    console.print("[bold]Triggering file import...[/bold]")
    success = service.trigger_import()

    if success:
        console.print("[green]File import triggered successfully[/green]")
    else:
        console.print("[red]Failed to trigger file import[/red]")
        raise typer.Exit(code=1)


@shoko_app.command("batch-rehash")
def batch_rehash() -> None:
    """Trigger CRC rehash for all files missing CRC32 hashes.

    Scans all Shoko files and triggers a rehash for any file that
    lacks a real CRC32 hash (either in filename or stored hash data).
    This is needed when CRC hash generation wasn't enabled in Shoko
    when files were first imported, leaving filenames with [%CRC]
    placeholders instead of actual CRC32 values like [350F23E7].
    """
    service = _get_service()

    console.print(
        "[bold]Scanning all files and triggering rehash for those "
        "missing CRC32 hashes...[/bold]\n"
        "[dim]This may take a while for large libraries.[/dim]"
    )

    result = service.batch_rehash_missing_crc()

    console.print(
        f"\n[bold]Batch Rehash Results[/bold]\n"
        f"  Files needing rehash: {result.total}\n"
        f"  [green]Succeeded: {result.succeeded}[/green]\n"
        f"  [red]Failed:     {result.failed}[/red]"
    )

    if result.total == 0:
        console.print("\n[green]All files already have CRC32 hashes![/green]")
        return

    if result.failed > 0:
        console.print("\n[bold red]Failed files:[/bold red]")
        for r in result.results:
            if not r.success:
                console.print(f"  [red]File {r.key}: {r.title} - {r.error}[/red]")

    console.print(
        "\n[dim]Rehashes are queued in Shoko and process in the background. "
        "Run 'shoko crc-audit' later to check progress.[/dim]"
    )


@shoko_app.command("season-gaps")
def season_gaps(
    section: Annotated[
        str, typer.Option("--section", "-s", help="Library section name")
    ] = "Anime",
    show_missing_only: Annotated[
        bool, typer.Option("--missing-only", help="Only show shows with missing seasons.")
    ] = False,
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Cross-reference Shoko series with Plex to find missing seasons.

    Groups Shoko series by TMDB show ID, then matches each group to
    a Plex show to identify seasons that exist in Shoko but not in Plex.
    """
    from plexctl.client import PlexClient
    from plexctl.config import load_config
    from plexctl.converters import season_gap_to_csv
    from plexctl.services.triage import TriageService

    console.print(
        f"[bold]Analyzing season gaps for section '{section}'...[/bold]\n"
        "  Cross-referencing Shoko series with Plex seasons..."
    )

    config = load_config()
    plex_client = PlexClient(config)
    shoko_service = _get_service()

    service = TriageService(plex_client, shoko_service=shoko_service)
    result = service.find_season_gaps(section)

    # Filter if requested
    gaps = result.gaps
    if show_missing_only:
        gaps = [g for g in gaps if g.is_missing]

    if not gaps:
        console.print("[green]✓ No season gaps found![/green]")
        return

    # CSV output
    if output_csv(gaps, season_gap_to_csv, csv_output, output):
        return

    # Print summary
    console.print(f"\n{result.summary}\n")

    # Print header table with gap summary
    gap_table = Table(title="Season Gaps")
    gap_table.add_column("Plex Show", style="green", max_width=35)
    gap_table.add_column("TMDB ID", style="dim", width=8)
    gap_table.add_column("Shoko Series", style="blue", max_width=40)
    gap_table.add_column("Plex", style="cyan", width=6, justify="right")
    gap_table.add_column("Expected", style="yellow", width=8, justify="right")
    gap_table.add_column("Missing", style="red", width=7, justify="right")
    gap_table.add_column("Status", width=8)

    for gap in gaps:
        status = "[red]MISSING[/red]" if gap.is_missing else "[green]OK[/green]"
        deficit = gap.expected_episode_count - gap.actual_episode_count
        shoko_names = ", ".join(f"{s.name} ({s.episode_count}ep)" for s in gap.shoko_series)

        gap_table.add_row(
            gap.plex_title,
            str(gap.tmdb_show_id or "-"),
            shoko_names,
            str(gap.actual_episode_count),
            str(gap.expected_episode_count),
            str(deficit) if deficit > 0 else "-",
            status,
        )

    console.print(gap_table)

    # Show detail for missing shows
    missing_gaps = [g for g in gaps if g.is_missing]
    if missing_gaps:
        console.print("\n[bold]Missing Season Details:[/bold]")
        for gap in missing_gaps[:15]:
            console.print(f"\n  [green]{gap.plex_title}[/green] (TMDB: {gap.tmdb_show_id})")
            console.print(
                f"    Plex: {gap.actual_episode_count} eps "
                f"across {len(gap.plex_seasons)} season(s)"
            )
            for season in gap.plex_seasons:
                console.print(
                    f"      S{season.season_number:02d}: "
                    f"{season.title} ({season.episode_count} eps)"
                )
            console.print(
                f"    Shoko: {gap.expected_episode_count} eps "
                f"across {len(gap.shoko_series)} series"
            )
            for s in gap.shoko_series:
                in_plex = "[green]✓[/green]" if gap.plex_key else "[dim]?[/dim]"
                console.print(
                    f"      {in_plex} {s.name} " f"(AniDB: {s.anidb_id}, {s.episode_count} eps)"
                )
            deficit = gap.expected_episode_count - gap.actual_episode_count
            console.print(f"    [red]Missing: {deficit} episodes[/red]")


@shoko_app.command("update-media-info")
def update_media_info() -> None:
    """Trigger Shoko to update all media info (codec analysis etc)."""
    service = _get_service()

    console.print("[bold]Triggering media info update for all files...[/bold]")
    success = service.trigger_update_media_info()

    if success:
        console.print("[green]Media info update triggered successfully[/green]")
    else:
        console.print("[red]Failed to trigger media info update[/red]")
        raise typer.Exit(code=1)


@shoko_app.command("plexmatch")
def plexmatch(
    series_id: Annotated[int, typer.Argument(help="Shoko series ID to generate .plexmatch for")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Output file path. Defaults to stdout.")
    ] = None,
    write_to_dir: Annotated[
        str | None,
        typer.Option(
            "--write-to-dir",
            "-w",
            help=(
                "Write .plexmatch directly into this directory "
                "(uses media_root + series name by default)"
            ),
        ),
    ] = None,
    ordering: Annotated[
        str | None,
        typer.Option(
            "--ordering",
            help=(
                "TMDB episode ordering ID for alternate season structure "
                "(e.g. '62f98314175051007c594bdf' for One Piece TVDB Order). "
                "Use 'shoko orderings' command to discover available options."
            ),
        ),
    ] = None,
    append: Annotated[
        bool,
        typer.Option(
            "--append",
            help=(
                "Merge with existing .plexmatch file. New entries override "
                "existing entries with the same season/episode. Only works "
                "with --write-to-dir."
            ),
        ),
    ] = False,
) -> None:
    """Generate a .plexmatch file for a series using Shoko data.

    Gathers series metadata (title, year, external IDs) and file-to-episode
    mappings from Shoko to produce a .plexmatch file. This file can be placed
    in the series directory for Plex to use during scanning.

    Ordering selection priority:
    1. --ordering flag (overrides preferences)
    2. Per-show preferences set via 'plexctl shoko plexmatch-prefer'
    3. No ordering (uses Shoko's default TMDB mapping)

    Use --append with --write-to-dir to preserve existing episode entries in
    an existing .plexmatch file — new entries override duplicates by key.

    Examples:
        plexctl shoko plexmatch 42
        plexctl shoko plexmatch 42 --write-to-dir /mnt/nfs/media/anime/Witch\\ watch
        plexctl shoko plexmatch 42 -o .plexmatch
        plexctl shoko plexmatch 75 --ordering 62f98314175051007c594bdf
        plexctl shoko plexmatch 42 -w /mnt/nfs/media/anime/Witch\\ Watch --append
    """
    service = _get_service()

    # Verify the series exists
    try:
        series_data = service.get_series(series_id)
    except Exception as exc:
        console.print(f"[red]Error: Could not find series {series_id}: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[bold]Generating .plexmatch for '{series_data.name}' (ID: {series_id})[/bold]"
    )

    # Resolve ordering: explicit CLI flag > per-show preference cache > None
    resolved_ordering = ordering
    if not resolved_ordering and series_data.ids.tmdb_show:
        from plexctl.ordering_cache import get_ordering_preference

        resolved_ordering = get_ordering_preference(series_data.ids.tmdb_show[0])

    # Determine plexmatch_dir for relative path computation
    plexmatch_dir = None
    if write_to_dir:
        plexmatch_dir = Path(write_to_dir).name

    plexmatch_result = service.generate_plexmatch(
        series_id,
        plexmatch_dir=plexmatch_dir,
        ordering_id=resolved_ordering,
        append=append,
        append_dir=write_to_dir,
    )
    content = plexmatch_result.render()

    # Determine output destination
    if write_to_dir:
        target_dir = Path(write_to_dir)
        target_file = target_dir / ".plexmatch"
        target_file.write_text(content, encoding="utf-8")
        console.print(f"[green].plexmatch written to {target_file}[/green]")
    elif output:
        output.write_text(content, encoding="utf-8")
        console.print(f"[green].plexmatch written to {output}[/green]")
    else:
        console.print(content)


@shoko_app.command("orderings", no_args_is_help=True)
def plexmatch_orderings(
    series_id: Annotated[int, typer.Argument(help="Shoko series ID to list orderings for")],
) -> None:
    """List available TMDB episode orderings for a series.

    Shows all alternate season structures (episode groups) available for
    a show on TMDB. Each ordering defines a different way to split episodes
    into seasons. Use the OrderingID with --ordering on plexmatch/plexmatch-all.

    For example, One Piece has "Sagas" (12 seasons), "TVDB Order" (23 seasons),
    "Seasons (Production)" (25 seasons), etc.

    Example:
        plexctl shoko orderings 75
    """
    service = _get_service()

    # Get the series to find its TMDB show ID
    try:
        series_data = service.get_series(series_id)
    except Exception as exc:
        console.print(f"[red]Error: Could not find series {series_id}: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    tmdb_id = series_data.ids.tmdb_show[0] if series_data.ids.tmdb_show else None
    if not tmdb_id:
        console.print(
            f"[yellow]Series '{series_data.name}' (ID: {series_id}) has no "
            f"TMDB show link. Link one with 'link-tmdb' first.[/yellow]"
        )
        raise typer.Exit()

    console.print(
        f"[bold]TMDB episode orderings for '{series_data.name}' "
        f"(TMDB show {tmdb_id})[/bold]\n"
    )

    orderings = service.list_tmdb_orderings(tmdb_id)

    if not orderings:
        console.print("[yellow]No alternate orderings found.[/yellow]")
        return

    table = Table(title=f"Episode Orderings ({len(orderings)} found)")
    table.add_column("Ordering ID", style="cyan", max_width=28)
    table.add_column("Name", style="green")
    table.add_column("Seasons", style="yellow", justify="right")
    table.add_column("Episodes", style="magenta", justify="right")
    table.add_column("Flags", style="dim")

    for o in orderings:
        flags = []
        if o.is_default:
            flags.append("default")
        if o.is_preferred:
            flags.append("preferred")
        if o.in_use:
            flags.append("in-use")

        table.add_row(
            o.ordering_id,
            o.name,
            str(o.season_count),
            str(o.episode_count),
            ", ".join(flags) if flags else "",
        )

    console.print(table)
    console.print(
        "\n[dim]Use the Ordering ID with " "--ordering flag on plexmatch/plexmatch-all.[/dim]"
    )


@shoko_app.command("plexmatch-prefer", no_args_is_help=True)
def plexmatch_prefer(
    series_id: Annotated[
        int, typer.Argument(help="Shoko series ID to set ordering preference for")
    ],
    ordering: Annotated[
        str,
        typer.Option(
            "--ordering",
            "-o",
            help=(
                "TMDB episode ordering ID to use as preference "
                "(e.g. '641eb9d6b234b9007ac67063'). "
                "Use 'plexmatch-orderings' command to discover available orderings."
            ),
        ),
    ],
    remove: Annotated[
        bool,
        typer.Option(
            "--remove",
            "-r",
            help="Remove the stored preference for this series instead of setting one.",
        ),
    ] = False,
) -> None:
    """Set or remove a preferred TMDB ordering for a series.

    Stores a preference mapping the series' TMDB show ID to the given
    ordering ID. This preference is used by plexmatch-all to automatically
    select the correct episode ordering for multi-season anime.

    Use 'shoko orderings' to discover available ordering IDs for a series.

    Examples:
        plexctl shoko plexmatch-prefer 75 --ordering 62f98314175051007c594bdf
        plexctl shoko plexmatch-prefer 42 --ordering 641eb9d6b234b9007ac67063
        plexctl shoko plexmatch-prefer 42 --remove
    """
    from plexctl.ordering_cache import remove_ordering_preference, save_ordering_preference

    service = _get_service()

    # Verify the series exists and get its TMDB show ID
    try:
        series_data = service.get_series(series_id)
    except Exception as exc:
        console.print(f"[red]Error: Could not find series {series_id}: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    tmdb_id = series_data.ids.tmdb_show[0] if series_data.ids.tmdb_show else None
    if not tmdb_id:
        console.print(
            f"[yellow]Series '{series_data.name}' (ID: {series_id}) has no "
            f"TMDB show link. Link one with 'link-tmdb' first.[/yellow]"
        )
        raise typer.Exit()

    if remove:
        removed = remove_ordering_preference(tmdb_id)
        if removed:
            console.print(
                f"[green]Removed ordering preference for "
                f"'{series_data.name}' (TMDB show {tmdb_id})[/green]"
            )
        else:
            console.print(
                f"[yellow]No ordering preference stored for "
                f"'{series_data.name}' (TMDB show {tmdb_id})[/yellow]"
            )
        return

    # Verify the ordering exists for this TMDB show
    orderings = service.list_tmdb_orderings(tmdb_id)
    valid_ids = {o.ordering_id for o in orderings}

    if ordering not in valid_ids:
        console.print(
            f"[red]Error: Ordering '{ordering}' is not valid for "
            f"'{series_data.name}' (TMDB show {tmdb_id}).[/red]\n"
            f"Use 'plexctl shoko orderings {series_id}' to list available orderings."
        )
        raise typer.Exit(code=1)

    path = save_ordering_preference(tmdb_id, ordering)
    ordering_name = next((o.name for o in orderings if o.ordering_id == ordering), ordering)
    console.print(
        f"[green]Saved ordering preference for "
        f"'{series_data.name}' (TMDB show {tmdb_id}):[/green]\n"
        f"  Ordering: {ordering_name} ({ordering})\n"
        f"  Cache: {path}"
    )


@shoko_app.command("plexmatch-all", no_args_is_help=True)
def plexmatch_all(
    library: Annotated[
        str, typer.Option(help="Library subdirectory within media root (e.g. 'anime', 'tv').")
    ] = "anime",
    media_root: Annotated[
        str | None,
        typer.Option(help="Root path for media files. Defaults to SHOKO_MEDIA_ROOT env var."),
    ] = None,
    ordering: Annotated[
        str | None,
        typer.Option(
            "--ordering",
            help=(
                "TMDB episode ordering ID for alternate season structure. "
                "Applied to ALL series (overrides per-show preferences). "
                "When omitted, uses preferences set via 'plexmatch-prefer'. "
                "Use 'shoko orderings' to discover available orderings."
            ),
        ),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would be done without writing any files.")
    ] = False,
    append: Annotated[
        bool,
        typer.Option(
            "--append",
            help=(
                "Merge with existing .plexmatch files. New entries override "
                "existing entries with the same season/episode key."
            ),
        ),
    ] = False,
) -> None:
    """Generate .plexmatch files for all series in a library directory.

    Scans the specified library directory (within media_root), matches each
    series folder to a Shoko series by name, and writes a .plexmatch file
    in each series directory.

    Uses fuzzy name matching to handle differences between folder names and
    Shoko series names (punctuation, case, common suffixes).

    Ordering selection priority:
    1. --ordering flag (applies to ALL series, overrides preferences)
    2. Per-show preferences set via 'plexctl shoko plexmatch-prefer'
    3. No ordering (uses Shoko's default TMDB mapping)

    Use --append to preserve existing episode entries in .plexmatch files —
    new entries override duplicates by season/episode key.

    Examples:
        plexctl shoko plexmatch-all
        plexctl shoko plexmatch-all --library tv
        plexctl shoko plexmatch-all --ordering 62f98314175051007c594bdf
        plexctl shoko plexmatch-all --dry-run
        plexctl shoko plexmatch-all --append
    """
    from plexctl.plugins.shoko.client import ShokoClient
    from plexctl.plugins.shoko.config import load_shoko_config

    config = load_shoko_config()
    client = ShokoClient(config)
    service = ShokoService(client)

    # Determine media root
    root = media_root or config.media_root

    if dry_run:
        console.print(
            f"[bold]DRY RUN[/bold] - Showing what would be done for "
            f"[cyan]{root}/{library}[/cyan]\n"
        )
    else:
        console.print(
            f"[bold]Generating .plexmatch files for " f"[cyan]{root}/{library}[/cyan][/bold]\n"
        )

    if not dry_run:
        result = service.generate_plexmatch_all(
            root, library=library, ordering_id=ordering, append=append
        )
    else:
        result = _dry_run_plexmatch_all(service, root, library)

    # Display results
    if not result.results:
        console.print("[yellow]No series directories found.[/yellow]")
        return

    # Summary table
    table = Table(title="PlexMatch Generation Results")
    table.add_column("Status", style="bold")
    table.add_column("Folder", style="green", max_width=40)
    table.add_column("Shoko Series", style="cyan", max_width=40)
    table.add_column("ID", style="yellow", justify="right")
    table.add_column("Episodes", style="magenta", justify="right")
    table.add_column("Detail", style="dim", max_width=40)

    for r in result.results:
        if r.success:
            status = "[green]✓[/green]"
            detail = f"{r.entry_count} episodes"
        elif r.series_id == 0:
            status = "[yellow]⊘[/yellow]"
            detail = r.error or "No match"
        else:
            status = "[red]✗[/red]"
            detail = r.error or "Failed"

        table.add_row(
            status,
            r.folder_name,
            r.series_name or "[dim]—[/dim]",
            str(r.series_id) if r.series_id else "[dim]—[/dim]",
            str(r.entry_count) if r.entry_count else "[dim]—[/dim]",
            detail,
        )

    console.print(table)

    # Print summary
    console.print(
        f"\n[bold]Summary[/bold]\n"
        f"  Directories scanned: {result.total_dirs}\n"
        f"  [green]Matched:[/green]       {result.matched}\n"
        f"  [green]Generated:[/green]     {result.generated}\n"
        f"  [red]Failed:[/red]         {result.failed}\n"
        f"  [yellow]Skipped:[/yellow]       {result.skipped}"
    )

    if dry_run:
        console.print("\n[dim]This was a dry run. No files were written.[/dim]")


def _dry_run_plexmatch_all(
    service: ShokoService, media_root: str, library: str
) -> PlexMatchBatchResult:
    """Perform a dry-run match of library dirs to Shoko series.

    Matches directories to series but does not generate or write files.
    Shows which directories would be grouped by TMDB show ID.
    """
    from pathlib import Path

    scan_dir = Path(media_root) / library if library else Path(media_root)

    if not scan_dir.is_dir():
        return PlexMatchBatchResult(total_dirs=0, results=[], failed=1)

    series_dirs = sorted(
        entry for entry in scan_dir.iterdir() if entry.is_dir() and not entry.name.startswith(".")
    )

    if not series_dirs:
        return PlexMatchBatchResult(total_dirs=0, results=[])

    # Fetch all Shoko series
    all_shoko_series: list[ShokoSeries] = []
    page = 1
    total = None
    while total is None or len(all_shoko_series) < total:
        series_page, total = service.list_series(page=page, page_size=100)
        if not series_page:
            break
        all_shoko_series.extend(series_page)
        page += 1
        if page > (total // 100) + 2:
            break

    # Build lookup: normalized_name -> list of ShokoSeries
    name_to_series_list: dict[str, list[ShokoSeries]] = {}
    for s in all_shoko_series:
        key = ShokoService._normalize_name(s.name or "")
        if key:
            name_to_series_list.setdefault(key, []).append(s)

    # Build lookup: tmdb_show_id -> list of ShokoSeries
    tmdb_to_series: dict[int, list[ShokoSeries]] = {}
    for s in all_shoko_series:
        for show_tmdb_id in s.ids.tmdb_show:
            tmdb_to_series.setdefault(show_tmdb_id, []).append(s)

    # Match each directory
    results: list[PlexMatchResult] = []
    seen_tmdb_groups: set[int] = set()

    for dir_path in series_dirs:
        folder_name = dir_path.name
        normalized_folder = ShokoService._normalize_name(folder_name)

        matched_series_list = name_to_series_list.get(normalized_folder, [])

        if not matched_series_list:
            # Secondary pass: substring matching
            for key, s_list in name_to_series_list.items():
                if key in normalized_folder or normalized_folder in key:
                    matched_series_list = s_list
                    break

        if not matched_series_list:
            results.append(
                PlexMatchResult(
                    series_id=0,
                    series_name="",
                    folder_name=folder_name,
                    folder_path=str(dir_path),
                    success=False,
                    error="No matching Shoko series found",
                )
            )
            continue

        primary_series = matched_series_list[0]
        tmdb_id: int | None = (
            primary_series.ids.tmdb_show[0] if primary_series.ids.tmdb_show else None
        )

        if tmdb_id:
            if tmdb_id in seen_tmdb_groups:
                continue
            seen_tmdb_groups.add(tmdb_id)

            group = tmdb_to_series.get(tmdb_id, [])
            series_count = len(group)
            note = f"Would generate (dry run) — {series_count} series grouped"
        else:
            note = "Would generate (dry run)"

        results.append(
            PlexMatchResult(
                series_id=primary_series.ids.id,
                series_name=primary_series.name or "",
                folder_name=folder_name,
                folder_path=str(dir_path),
                success=True,
                error=note,
            )
        )

    matched = sum(1 for r in results if r.series_id > 0)
    skipped = sum(1 for r in results if r.series_id == 0)

    return PlexMatchBatchResult(
        total_dirs=len(series_dirs),
        matched=matched,
        generated=0,
        failed=0,
        skipped=skipped,
        results=results,
    )
