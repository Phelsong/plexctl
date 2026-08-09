"""Typer CLI commands for unified triage, diagnostics, fixes, and filesystem checks.

Provides a single triage command group that consolidates:
- Cross-referenced triage reports (Plex + filesystem)
- Plex media diagnostics (scan, show, files)
- Filesystem comparison (fsck-scan, fsck-orphans, fsck-grouped,
  fsck-reorganize)
- CSV ingest
"""

from __future__ import annotations

from pathlib import Path as FilePath
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from plexctl.client import PlexClient
from plexctl.commands._helpers import output_csv, print_batch_result, print_result, run_ingest
from plexctl.config import load_config
from plexctl.converters import (
    fs_dir_to_csv,
    media_part_detail_to_csv,
    show_diagnostics_to_csv,
    triage_issue_to_csv,
)
from plexctl.models import ReorgAction, TriageAction, TriageSeverity
from plexctl.options import CsvFlag, OutputFile  # noqa: TC001
from plexctl.services.diagnostics import DiagnosticService
from plexctl.services.fixes import FixService
from plexctl.services.fs_compare import FsCompareService
from plexctl.services.plexmatch import PlexMatchService
from plexctl.services.server import ServerService
from plexctl.services.triage import TriageService

triage_app = typer.Typer(
    name="triage",
    help="Unified diagnostics, fixes, and filesystem checks for Plex.",
    no_args_is_help=True,
)
console = Console()


# ---------------------------------------------------------------------------
# Service factories
# ---------------------------------------------------------------------------


def _get_diagnostic_service() -> DiagnosticService:
    """Load config and create a connected DiagnosticService."""
    config = load_config()
    client = PlexClient(config)
    return DiagnosticService(client)


def _get_fix_service() -> FixService:
    """Load config and create a connected FixService."""
    config = load_config()
    client = PlexClient(config)
    return FixService(client)


def _get_fs_service(path_map: dict[str, str] | None = None) -> FsCompareService:
    """Load config and create a connected FsCompareService."""
    config = load_config()
    client = PlexClient(config)
    return FsCompareService(client, path_map=path_map)


def _get_server_service() -> ServerService:
    """Load config and create a connected ServerService."""
    config = load_config()
    client = PlexClient(config)
    return ServerService(client)


def _get_plexmatch_service() -> PlexMatchService:
    """Load config and create a connected PlexMatchService."""
    config = load_config()
    client = PlexClient(config)
    return PlexMatchService(client)


# ---------------------------------------------------------------------------
# Path map parsers
# ---------------------------------------------------------------------------


def _parse_path_map(path_map: list[str] | None) -> dict[str, str]:
    """Parse path map strings like '/data=/mnt/nfs/media' into a dict.

    Accepts a list of individual mapping strings (for the report command).
    """
    if not path_map:
        return {}
    result: dict[str, str] = {}
    for mapping in path_map:
        if "=" not in mapping:
            console.print(
                f"[yellow]Invalid path map '{mapping}', expected format: "
                "/server/path=/local/path[/yellow]"
            )
            continue
        server_path, local_path = mapping.split("=", 1)
        result[server_path] = local_path
    return result


def _parse_path_map_str(path_map_str: str | None) -> dict[str, str] | None:
    """Parse a comma-separated path map string into a dict.

    Accepts a single comma-separated string like
    '/data=/mnt/nfs/media,/opt=/mnt/nfs/opt'.
    Returns None when the input is empty or None.
    """
    if not path_map_str:
        return None
    result: dict[str, str] = {}
    for mapping in path_map_str.split(","):
        parts = mapping.strip().split("=", 1)
        if len(parts) == 2:
            result[parts[0].strip()] = parts[1].strip()
    return result if result else None


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _format_severity(severity: TriageSeverity) -> str:
    """Color-code severity for display."""
    colors = {
        TriageSeverity.CRITICAL: "bold red",
        TriageSeverity.ERROR: "red",
        TriageSeverity.WARNING: "yellow",
        TriageSeverity.INFO: "blue",
    }
    color = colors.get(severity, "white")
    return f"[{color}]{severity.value}[/{color}]"


def _format_action(action: TriageAction) -> str:
    """Color-code recommended action for display."""
    action_labels = {
        TriageAction.ANALYZE: "[green]analyze[/green]",
        TriageAction.REFRESH: "[cyan]refresh[/cyan]",
        TriageAction.FIX_MATCH: "[magenta]fix-match[/magenta]",
        TriageAction.LINK_TMDB: "[blue]link-tmdb[/blue]",
        TriageAction.REVIEW: "[yellow]review[/yellow]",
        TriageAction.REORGANIZE: "[bright_magenta]reorganize[/bright_magenta]",
        TriageAction.SHOKO_CONFIG: "[bright_blue]config[/bright_blue]",
    }
    return action_labels.get(action, str(action))


def _risk_style(risk: str) -> str:
    """Map risk level to Rich style string."""
    return {"low": "green", "medium": "yellow", "high": "red"}.get(risk, "white")


def _display_reorg_actions(actions: list[ReorgAction], title: str) -> None:
    """Display filtered reorganization actions in a grouped table format.

    Renders actions grouped by type (move, review, remove_empty) with
    risk-colored markers, source/destination columns, and reasons.
    Prints a summary line with action counts and recommended next steps.
    """
    if not actions:
        console.print("[green]No reorganization actions for these items.[/green]")
        return

    console.print(f"\n[bold]{title}[/bold]")

    action_types: dict[str, list[ReorgAction]] = {}
    for a in actions:
        action_types.setdefault(a.action, []).append(a)

    for action_type, type_actions in action_types.items():
        label = {
            "move": "[bold cyan] MOVE PROPOSALS[/bold cyan]",
            "review": "[bold yellow] REVIEW NEEDED[/bold yellow]",
            "remove_empty": "[bold green] CLEANUP[/bold green]",
        }.get(action_type, f"[bold]{action_type.upper()}[/bold]")
        console.print(f"\n{label}")

        table = Table()
        table.add_column("Risk", style="bold", width=6)
        table.add_column("Source", style="cyan")
        table.add_column("Destination", style="green")
        table.add_column("Reason", style="white")

        for a in type_actions:
            risk_marker = f"[{_risk_style(a.risk)}]{a.risk}[/{_risk_style(a.risk)}]"
            dest = a.destination or "-"
            table.add_row(risk_marker, a.source, dest, a.reason)

        console.print(table)

    # Summary
    move_count = len(action_types.get("move", []))
    review_count = len(action_types.get("review", []))
    cleanup_count = len(action_types.get("remove_empty", []))
    parts: list[str] = []
    if move_count:
        parts.append(f"{move_count} move")
    if review_count:
        parts.append(f"{review_count} review")
    if cleanup_count:
        parts.append(f"{cleanup_count} cleanup")
    console.print(f"\n[bold]Summary:[/bold] {', '.join(parts)} action(s)")
    if review_count:
        console.print(
            "  [yellow]Review actions require manual decisions " "before proceeding.[/yellow]"
        )
    if cleanup_count:
        console.print("  [green]Cleanup actions are safe — empty dirs can be removed.[/green]")


# ===================================================================
# Existing triage commands (report, fix, seasons)
# ===================================================================


@triage_app.command("report")
def report(
    section: Annotated[str, typer.Option(help="Library section name")] = "TV Shows",
    path_map: Annotated[
        list[str] | None,
        typer.Option(
            help="Path mapping (e.g. /data=/mnt/nfs/media). " "Can be specified multiple times."
        ),
    ] = None,
    filter_severity: Annotated[
        str | None, typer.Option(help="Filter by severity: error, warning, info")
    ] = None,
    filter_action: Annotated[
        str | None,
        typer.Option(
            help="Filter by recommended action: analyze, refresh, fix-match, "
            "link-tmdb, review, reorganize"
        ),
    ] = None,
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Generate a unified triage report combining all data sources.

    Cross-references Plex diagnostics and filesystem comparison to provide
    a comprehensive view of issues and actionable fix recommendations.
    """
    console.print(
        f"[bold]Running triage for section '{section}'...[/bold]\n"
        "  Querying Plex diagnostics and filesystem..."
    )

    config = load_config()
    plex_client = PlexClient(config)

    service = TriageService(plex_client)
    parsed_path_map = _parse_path_map(path_map)
    result = service.triage_section(section, path_map=parsed_path_map or None)

    if not result.issues:
        console.print(f"\n[green]✓ No issues found in section '{section}'![/green]")
        return

    # Apply filters
    filtered = result.issues
    if filter_severity:
        filtered = [i for i in filtered if i.severity.value == filter_severity]
    if filter_action:
        filtered = [i for i in filtered if i.action.value == filter_action]

    if not filtered:
        console.print("\n[yellow]No issues match the specified filters.[/yellow]")
        return

    # CSV output
    if output_csv(filtered, triage_issue_to_csv, csv_output, output):
        return

    # Print summary
    console.print(f"\n{result.summary}\n")

    # Print issues table
    table = Table(title="Triage Issues")
    table.add_column("#", style="dim", justify="right", width=4)
    table.add_column("Severity", justify="center", width=8)
    table.add_column("Type", style="yellow", width=16)
    table.add_column("Action", width=14)
    table.add_column("Plex Show", style="green", max_width=30)
    table.add_column("Detail", style="white", max_width=60)

    for idx, issue in enumerate(filtered, 1):
        table.add_row(
            str(idx),
            _format_severity(issue.severity),
            issue.issue_type.value,
            _format_action(issue.action),
            issue.plex_title or "[dim]-[/dim]",
            issue.detail,
        )
    console.print(table)

    # Print actionable steps
    auto_fixable = [i for i in filtered if i.action == TriageAction.ANALYZE]
    needs_review = [i for i in filtered if i.action == TriageAction.REVIEW]
    needs_reorg = [i for i in filtered if i.action == TriageAction.REORGANIZE]

    console.print("\n[bold]Recommended Actions:[/bold]")

    if auto_fixable:
        console.print(
            f"  [green]analyze[/green]: {len(auto_fixable)} shows need "
            f"re-analysis → run: [cyan]plexctl fix batch-analyze "
            f"--section {section}[/cyan]"
        )
    if needs_review:
        console.print(
            f"  [yellow]review[/yellow]: {len(needs_review)} issues need " f"manual inspection"
        )
    if needs_reorg:
        console.print(
            f"  [bright_magenta]reorganize[/bright_magenta]: {len(needs_reorg)} "
            f"directories need restructuring → run: "
            f"[cyan]plexctl fsck reorganize --section {section}[/cyan]"
        )


@triage_app.command("fix")
def run_fix(
    section: Annotated[str, typer.Option(help="Library section name")] = "Anime",
    action: Annotated[
        str, typer.Option(help="Only fix issues with this recommended action: analyze, refresh")
    ] = "analyze",
) -> None:
    """Execute auto-fixable triage actions.

    Currently supports:
    - analyze: Run batch analysis on unanalyzed shows.
    - refresh: Run batch metadata refresh on unanalyzed shows.
    """
    config = load_config()
    plex_client = PlexClient(config)
    fix_service = FixService(plex_client)

    if action == "analyze":
        console.print(f"[bold]Running batch analysis for section '{section}'...[/bold]")
        result = fix_service.batch_analyze(section, only_unanalyzed=True)

        print_batch_result(result)

        if result.succeeded > 0:
            console.print(
                "\n[dim]Analysis is asynchronous — Plex processes "
                "items in the background.[/dim]"
            )

    elif action == "refresh":
        console.print(f"[bold]Running batch refresh for section '{section}'...[/bold]")
        result = fix_service.batch_refresh(section, only_unanalyzed=True)

        print_batch_result(result)

    else:
        console.print(f"[red]Unknown action '{action}'. Supported: analyze, refresh[/red]")
        raise typer.Exit(1)


# ===================================================================
# Diagnostics commands (from diagnostics.py)
# ===================================================================


@triage_app.command("diagnose")
def diagnose_scan(
    section: str = typer.Option("Anime", help="Library section name to scan"),
    deep: bool = typer.Option(False, help="Include per-episode file details (slower)"),
    issues_only: bool = typer.Option(True, help="Only show shows with problems"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Scan a library section for shows with file parsing issues.

    Identifies unanalyzed media, cross-season merges, and missing files.
    """
    console.print(f"[bold]Scanning section '{section}'...[/bold]")
    service = _get_diagnostic_service()
    result = service.scan_section(section, deep=deep)

    # Summary header
    console.print()
    console.print(f"[bold]{result.title}[/bold] (key={result.key})")
    console.print(f"  Scanner: {result.scanner or 'unknown'}")
    console.print(f"  Agent:   {result.agent or 'unknown'}")
    console.print(f"  Paths:   {', '.join(result.section_locations)}")
    console.print(
        f"  Shows:   {result.total_shows} total, {result.shows_with_issues} with issues"
    )
    console.print()

    # Filter shows if issues_only
    shows = result.shows
    if issues_only:
        shows = [s for s in shows if s.unanalyzed_episodes > 0 or s.multi_media_episodes > 0]

    if output_csv(shows, show_diagnostics_to_csv, csv_output, output):
        return

    if not shows:
        console.print("[green]No issues found![/green]")
        return

    table = Table(title="Shows with Issues")
    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="green")
    table.add_column("Episodes", style="white", justify="right")
    table.add_column("Unanalyzed", style="red", justify="right")
    table.add_column("Multi-Media", style="yellow", justify="right")
    table.add_column("Missing Files", style="red", justify="right")
    table.add_column("Locations", style="dim")

    for show in shows:
        locations_str = "\n".join(show.locations) if show.locations else "-"
        table.add_row(
            show.key,
            show.title or "Unknown",
            str(show.total_episodes),
            str(show.unanalyzed_episodes),
            str(show.multi_media_episodes),
            str(show.missing_file_episodes),
            locations_str,
        )

    console.print(table)

    # If deep scan, show per-episode details for shows with issues
    if deep:
        for show in shows:
            problem_episodes = [
                ep for ep in show.episode_details if ep.has_unanalyzed or ep.media_count > 1
            ]
            if not problem_episodes:
                continue

            console.print(f"\n[bold]{show.title}[/bold] - Problem Episodes:")
            ep_table = Table()
            ep_table.add_column("S", style="cyan", justify="right", width=3)
            ep_table.add_column("E", style="cyan", justify="right", width=3)
            ep_table.add_column("Title", style="green")
            ep_table.add_column("Media", style="yellow", justify="right", width=5)
            ep_table.add_column("Issue", style="red")

            for ep in problem_episodes:
                issues: list[str] = []
                if ep.has_unanalyzed:
                    issues.append("unanalyzed")
                if ep.media_count > 1:
                    issues.append(f"{ep.media_count} media versions")

                ep_table.add_row(
                    str(ep.season_number or "?"),
                    str(ep.episode_number or "?"),
                    ep.title or "-",
                    str(ep.media_count),
                    ", ".join(issues),
                )

            console.print(ep_table)


@triage_app.command("diagnose-show")
def diagnose_show(
    key: str = typer.Argument(help="Plex rating key of the show"),
    deep: bool = typer.Option(True, help="Include per-episode file details"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Diagnose a single show by rating key."""
    service = _get_diagnostic_service()
    result = service.diagnose_show(key, deep=deep)

    if output_csv([result], show_diagnostics_to_csv, csv_output, output):
        return

    console.print(f"\n[bold]{result.title}[/bold] (key={result.key})")
    console.print(f"  Year: {result.year or 'unknown'}")
    console.print(f"  Locations: {', '.join(result.locations) or 'none'}")
    console.print(
        f"  Episodes: {result.total_episodes} total, "
        f"{result.unanalyzed_episodes} unanalyzed, "
        f"{result.multi_media_episodes} multi-media, "
        f"{result.missing_file_episodes} missing files"
    )

    if not result.episode_details:
        return

    # Show problem episodes
    problem_episodes = [
        ep for ep in result.episode_details if ep.has_unanalyzed or ep.media_count > 1
    ]

    if problem_episodes:
        console.print("\n[bold red]Problem Episodes:[/bold red]")
        for ep in problem_episodes:
            issues: list[str] = []
            if ep.has_unanalyzed:
                issues.append("unanalyzed")
            if ep.media_count > 1:
                issues.append(f"{ep.media_count} media versions")
            console.print(
                f"  S{ep.season_number or '?':0>2}"
                f"E{ep.episode_number or '?':0>2} "
                f"{ep.title or '-'} — {', '.join(issues)}"
            )

    # Deep: show file tree
    if deep and result.episode_details:
        console.print("\n[bold]File Details:[/bold]")
        tree = Tree(result.title or "Show")
        for ep in result.episode_details:
            if not ep.file_details:
                continue
            season_label = f"S{ep.season_number or '?':0>2}"
            episode_label = f"E{ep.episode_number or '?':0>2}"
            issue_marker = " [red]⚠[/red]" if (ep.has_unanalyzed or ep.media_count > 1) else ""
            ep_branch = tree.add(f"{season_label}{episode_label} {ep.title or '-'}{issue_marker}")
            for detail in ep.file_details:
                codec_info = []
                if detail.video_codec:
                    codec_info.append(detail.video_codec)
                if detail.audio_codec:
                    codec_info.append(detail.audio_codec)
                if detail.container:
                    codec_info.append(detail.container)
                codec_str = "/".join(codec_info) if codec_info else "[dim]no codecs[/dim]"

                missing_marker = ""
                if detail.exists is False:
                    missing_marker = " [red]MISSING[/red]"
                elif detail.accessible is False:
                    missing_marker = " [red]INACCESSIBLE[/red]"

                ep_branch.add(f"{detail.file_path} ({codec_str}){missing_marker}")
        console.print(tree)


@triage_app.command("diagnose-files")
def diagnose_files(
    key: str = typer.Argument(help="Plex rating key of the episode"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Show detailed file information for a specific episode."""
    service = _get_diagnostic_service()
    result = service.get_episode_details(key)

    if csv_output:
        if result.file_details:
            output_csv(result.file_details, media_part_detail_to_csv, csv_output, output)
        return

    console.print(f"\n[bold]{result.title or 'Episode ' + result.key}[/bold]")
    console.print(
        f"  Season {result.season_number or '?'}, " f"Episode {result.episode_number or '?'}"
    )
    console.print(f"  Media versions: {result.media_count}")
    console.print(f"  Unanalyzed: {'Yes' if result.has_unanalyzed else 'No'}")

    if not result.file_details:
        console.print("\n[dim]No file details available.[/dim]")
        return

    table = Table(title="File Details")
    table.add_column("Path", style="green")
    table.add_column("Video", style="cyan")
    table.add_column("Audio", style="yellow")
    table.add_column("Container", style="white")
    table.add_column("Resolution", style="magenta")
    table.add_column("Size", style="blue", justify="right")
    table.add_column("Status", style="red")

    for detail in result.file_details:
        status_parts: list[str] = []
        if detail.exists is False:
            status_parts.append("MISSING")
        if detail.accessible is False:
            status_parts.append("INACCESSIBLE")
        status = ", ".join(status_parts) if status_parts else "OK"

        size_str = "-"
        if detail.size is not None:
            size_str = f"{detail.size / (1024 * 1024):.1f} MB"

        table.add_row(
            detail.file_path,
            detail.video_codec or "[dim]none[/dim]",
            detail.audio_codec or "[dim]none[/dim]",
            detail.container or "[dim]none[/dim]",
            detail.resolution or "[dim]none[/dim]",
            size_str,
            status,
        )

    console.print(table)


@triage_app.command("analyze")
def analyze_item(
    key: Annotated[str | None, typer.Argument(help="Plex rating key of the item")] = None,
    section: Annotated[
        str | None, typer.Option(help="Section name to analyze (instead of item)")
    ] = None,
) -> None:
    """Trigger Plex to re-analyze a media item or section.

    Provide either a rating key for a single item, or --section to
    analyze all items in a section.
    """
    if not key and not section:
        console.print("[red]Provide a rating key or --section name[/red]")
        raise typer.Exit(1)

    service = _get_diagnostic_service()
    if section:
        result = service.trigger_section_analyze(section)
    elif key:
        result = service.trigger_analyze(key)
    else:
        console.print("[red]Provide a rating key or --section name[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ {result}[/green]")


# ===================================================================
# Fixes commands (from fixes.py)
# ===================================================================


@triage_app.command("batch-analyze")
def batch_analyze(
    section: str = typer.Option("Anime", help="Library section name"),
    only_unanalyzed: bool = typer.Option(
        True, help="Only analyze shows with unanalyzed episodes"
    ),
) -> None:
    """Re-analyze all shows with problems in a section.

    Targets only shows that have unanalyzed or multi-media episodes,
    triggering Plex's background analysis on each. Much more targeted
    than refreshing the entire section.
    """
    service = _get_fix_service()
    result = service.batch_analyze(section, only_unanalyzed=only_unanalyzed)

    print_batch_result(result, title=f"Batch Analyze: {section}")

    if result.succeeded > 0:
        console.print(
            "\n[dim]Analysis is asynchronous — Plex processes " "items in the background.[/dim]"
        )


@triage_app.command("batch-refresh")
def batch_refresh(
    section: str = typer.Option("Anime", help="Library section name"),
    only_unanalyzed: bool = typer.Option(
        True, help="Only refresh shows with unanalyzed episodes"
    ),
) -> None:
    """Refresh metadata for all shows with problems in a section.

    Like batch-analyze but triggers a full metadata refresh (redownloads
    from the agent). Heavier than analysis but can fix more issues.
    """
    service = _get_fix_service()
    result = service.batch_refresh(section, only_unanalyzed=only_unanalyzed)

    print_batch_result(result, title=f"Batch Refresh: {section}")


@triage_app.command("refresh")
def refresh_item(
    key: Annotated[str | None, typer.Argument(help="Plex rating key of the item")] = None,
    section: Annotated[str | None, typer.Option(help="Section name to refresh all items")] = None,
) -> None:
    """Refresh metadata for an item or entire section.

    Provide a rating key for a single item, or --section to
    refresh all items in a section (can be slow for large libraries).
    """
    if not key and not section:
        console.print("[red]Provide a rating key or --section name[/red]")
        raise typer.Exit(1)

    service = _get_fix_service()
    if section:
        result = service.refresh_section(section)
    elif key:
        result = service.refresh_item(key)
    else:
        console.print("[red]Provide a rating key or --section name[/red]")
        raise typer.Exit(1)

    if result.success:
        console.print(f"[green]✓ {result.action}: '{result.title}' (key={result.key})[/green]")
    else:
        console.print(
            f"[red]✗ {result.action} failed for '{result.title}' (key={result.key}): "
            f"{result.error}[/red]"
        )
        raise typer.Exit(1)


@triage_app.command("scan")
def fixes_scan(
    section: str = typer.Option("Anime", help="Library section name to scan"),
    path: Annotated[
        str | None, typer.Option(help="Specific path within the section to scan")
    ] = None,
) -> None:
    """Scan a library section for new or changed files.

    This tells Plex to look for new media files in the section's
    filesystem paths. Use --path to scan only a specific subfolder.
    """
    service = _get_fix_service()
    result = service.scan_section(section, path=path)

    if result.success:
        path_info = f" (path: {path})" if path else ""
        console.print(f"[green]✓ Scan triggered for section '{result.title}'{path_info}[/green]")
    else:
        console.print(f"[red]✗ Scan failed for section '{result.title}': {result.error}[/red]")
        raise typer.Exit(1)


@triage_app.command("split")
def split_show(
    key: str = typer.Argument(help="Plex rating key of the multi-location show to split"),
) -> None:
    """Split a multi-location show into separate entries.

    When Plex merges multiple filesystem directories into one show (e.g
    different seasons stored in separate folders), this command splits
    them back into individual shows with their own metadata.
    """
    service = _get_fix_service()
    result = service.split_show(key)

    if result.success:
        matched_info = f" → {result.matched_to}" if result.matched_to else ""
        console.print(
            f"[green]✓ Split show '{result.title}' " f"(key={result.key}){matched_info}[/green]"
        )
    else:
        console.print(
            f"[red]✗ Failed to split '{result.title}' "
            f"(key={result.key}): {result.error}[/red]"
        )
        raise typer.Exit(1)


@triage_app.command("remove-duplicates")
def remove_duplicates(
    section: str = typer.Option("Anime", help="Library section name"),
    dry_run: bool = typer.Option(
        True, help="Only show what would be deleted without actually deleting."
    ),
) -> None:
    """Remove duplicate media versions from episodes.

    Scans a section for episodes with multiple media versions (caused
    by cross-season file matching) and removes the duplicates, keeping
    only the first version. Use --no-dry-run to actually delete.

    By default, runs in dry-run mode to preview changes.
    """
    service = _get_fix_service()
    result = service.remove_duplicate_media(section, dry_run=dry_run)

    mode_label = "DRY RUN" if dry_run else "LIVE"
    console.print(
        f"\n[bold]Remove Duplicate Media: {section} "
        f"([bold yellow]{mode_label}[/bold yellow])[/bold]"
    )
    console.print(f"  Episodes with duplicates: {result.total}")
    console.print(f"  Would remove:             [green]{result.succeeded}[/green]")
    console.print(f"  Failed:                   [red]{result.failed}[/red]")

    if result.results:
        console.print("\n[bold]Details:[/bold]")
        for r in result.results:
            status = "[green]✓[/green]" if r.success else "[red]✗[/red]"
            console.print(f"  {status} {r.title} (key={r.key})")

    if not dry_run and result.succeeded > 0:
        console.print(
            "\n[dim]Duplicates have been removed. "
            "Run 'fix batch-analyze' to re-analyze affected episodes.[/dim]"
        )
    elif dry_run and result.succeeded > 0:
        console.print(
            "\n[dim]This was a dry run. Use --no-dry-run to actually "
            "remove duplicate media versions.[/dim]"
        )


@triage_app.command("matches")
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


@triage_app.command("fix-match")
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


@triage_app.command("unmatch")
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


# ===================================================================
# Filesystem comparison commands (from fs_compare.py)
# ===================================================================


@triage_app.command("fsck-scan")
def fsck_scan(
    section: str = typer.Option("Anime", help="Library section name to scan"),
    path_map: str | None = typer.Option(
        None, help="Path mapping from Plex to local, e.g. '/data=/mnt/nfs/media'"
    ),
    depth: int = typer.Option(2, help="Maximum directory depth to walk"),
    count_files: bool = typer.Option(
        False, help="Count video files in each dir (slow on network mounts)"
    ),
    orphans: bool = typer.Option(True, help="Show orphaned directories"),
    grouped: bool = typer.Option(True, help="Show directories with grouping risk"),
    multi_loc: bool = typer.Option(True, help="Show shows with multiple locations"),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Compare a section's filesystem with Plex's show locations.

    Walks the section root directories on disk and cross-references
    with Plex's known show locations to identify mismatches.
    """
    console.print(f"[bold]Comparing filesystem with Plex for '{section}'...[/bold]")
    pm = _parse_path_map_str(path_map)
    service = _get_fs_service(path_map=pm)
    result = service.compare_section(section, max_depth=depth, count_files=count_files)

    # Summary header
    console.print()
    console.print(f"[bold]{result.section_title}[/bold]")
    console.print(f"  Scanner:    {result.scanner or 'unknown'}")
    console.print(f"  Root paths: {result.section_root}")
    console.print(
        f"  Directories: {result.total_dirs} found, "
        f"{result.plex_tracked_dirs} tracked by Plex"
    )
    console.print()

    # CSV: output all directories as CSV
    if csv_output:
        all_dirs = result.orphan_dirs + result.grouped_dirs
        if output_csv(all_dirs, fs_dir_to_csv, csv_output, output):
            return

    # Multi-location shows
    if multi_loc and result.multi_location_shows:
        console.print("[bold yellow]Shows with Multiple Locations:[/bold yellow]")
        console.print(
            "[dim]These Plex shows reference multiple filesystem directories."
            " This happens when metadata sources merge separate entries.[/dim]"
        )
        table = Table()
        table.add_column("Show", style="green")
        table.add_column("Locations", style="cyan")

        for show_title, locations in result.multi_location_shows:
            table.add_row(show_title, "\n".join(locations))

        console.print(table)
        console.print()

    # Grouped directories (grouping risk)
    if grouped and result.grouped_dirs:
        console.print("[bold red]Grouping Risk Directories:[/bold red]")
        console.print(
            "[dim]These directories have both video files AND subdirectories."
            " These can be resolved by removing them from Plex's grouping,"
            " but the files and subdirs may end up as separate series.[/dim]"
        )
        table = Table()
        table.add_column("Directory", style="green")
        table.add_column("Files", style="yellow", justify="right")
        table.add_column("Subdirs", style="cyan", justify="right")
        table.add_column("Subdirectory Names", style="dim")
        table.add_column("Plex Shows", style="magenta")

        for fs_dir in result.grouped_dirs:
            plex_info = (
                ", ".join(fs_dir.plex_shows) if fs_dir.plex_shows else "[red]NOT TRACKED[/red]"
            )
            file_display = (
                str(fs_dir.video_files)
                if fs_dir.video_files > 0
                else "yes" if fs_dir.has_files else "0"
            )
            table.add_row(
                fs_dir.name,
                file_display,
                str(fs_dir.subdir_count),
                ", ".join(fs_dir.subdirs[:5]) + ("..." if len(fs_dir.subdirs) > 5 else ""),
                plex_info,
            )

        console.print(table)
        console.print()

    # Orphaned directories
    if orphans and result.orphan_dirs:
        console.print("[bold red]Orphaned Directories:[/bold red]")
        console.print(
            "[dim]These directories exist on disk but Plex doesn't track them"
            " as show locations. They may contain files the metadata source couldn't match.[/dim]"
        )
        table = Table()
        table.add_column("Directory", style="green")
        table.add_column("Files", style="yellow", justify="right")
        table.add_column("Subdirs", style="cyan", justify="right")
        table.add_column("Subdirectory Names", style="dim")

        # Separate: orphans with files vs orphans that are empty.
        with_files = [d for d in result.orphan_dirs if d.video_files > 0 or d.has_files]
        empty = [d for d in result.orphan_dirs if d.video_files == 0 and not d.has_files]

        if with_files:
            console.print("\n[bold]With files (potentially untracked content):[/bold]")
            for fs_dir in with_files:
                file_display = str(fs_dir.video_files) if fs_dir.video_files > 0 else "yes"
                table.add_row(
                    fs_dir.name,
                    file_display,
                    str(fs_dir.subdir_count),
                    ", ".join(fs_dir.subdirs[:5]) + ("..." if len(fs_dir.subdirs) > 5 else ""),
                )
            console.print(table)

        if empty:
            console.print(f"\n[dim]{len(empty)} empty directories not tracked by Plex.[/dim]")
        console.print()

    if not result.orphan_dirs and not result.grouped_dirs and not result.multi_location_shows:
        console.print(
            "[green]No issues found! All directories match Plex show locations.[/green]"
        )


@triage_app.command("fsck-orphans")
def fsck_orphans(
    section: str = typer.Option("Anime", help="Library section name"),
    path_map: str | None = typer.Option(
        None, help="Path mapping from Plex to local, e.g. '/data=/mnt/nfs/media'"
    ),
    with_files_only: bool = typer.Option(False, help="Only show orphans that contain files"),
    force: bool = typer.Option(
        False, help="Show reorganization commands (review + cleanup) for orphans"
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List directories on disk that Plex doesn't track.

    With --force, generates a reorganization plan and displays review
    and cleanup actions for the orphaned directories found.
    """
    pm = _parse_path_map_str(path_map)
    service = _get_fs_service(path_map=pm)
    orphans = service.list_orphans(section)

    if with_files_only:
        orphans = [d for d in orphans if d.video_files > 0 or d.has_files]

    if output_csv(orphans, fs_dir_to_csv, csv_output, output):
        return

    if not orphans:
        console.print("[green]No orphaned directories found.[/green]")
        return

    if force:
        orphan_paths = {d.path for d in orphans}
        plan = service.reorganize_plan(section)
        filtered_actions = [
            a
            for a in plan.actions
            if a.action in ("review", "remove_empty") and a.source in orphan_paths
        ]
        _display_reorg_actions(
            filtered_actions,
            title=f"Reorganization Actions for {len(orphans)} Orphaned Directories",
        )
        return

    table = Table(title="Orphaned Directories")
    table.add_column("Directory", style="green")
    table.add_column("Files", style="yellow", justify="right")
    table.add_column("Subdirs", style="cyan", justify="right")
    table.add_column("Subdirectory Names", style="dim")

    for fs_dir in orphans:
        table.add_row(
            fs_dir.name,
            str(fs_dir.video_files),
            str(fs_dir.subdir_count),
            ", ".join(fs_dir.subdirs[:5]) + ("..." if len(fs_dir.subdirs) > 5 else ""),
        )

    console.print(table)


@triage_app.command("fsck-grouped")
def fsck_grouped(
    section: str = typer.Option("Anime", help="Library section name"),
    path_map: str | None = typer.Option(
        None, help="Path mapping from Plex to local, e.g. '/data=/mnt/nfs/media'"
    ),
    force: bool = typer.Option(
        False, help="Show reorganization commands (move actions) for grouped dirs"
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """List directories with both files+subdirectories (grouping risk).

    With --force, generates a reorganization plan and displays move
    actions for the grouped directories found.
    """
    pm = _parse_path_map_str(path_map)
    service = _get_fs_service(path_map=pm)
    grouped = service.list_grouped(section)

    if output_csv(grouped, fs_dir_to_csv, csv_output, output):
        return

    if not grouped:
        console.print("[green]No grouping risk directories found.[/green]")
        return

    if force:
        grouped_paths = {d.path for d in grouped}
        plan = service.reorganize_plan(section)
        filtered_actions = [
            a
            for a in plan.actions
            if a.action == "move" and any(a.source.startswith(p + "/") for p in grouped_paths)
        ]
        _display_reorg_actions(
            filtered_actions,
            title=(f"Reorganization Actions for {len(grouped)} Grouping-Risk Directories"),
        )
        return

    tree = Tree("[bold]Directories with Files + Subdirs[/bold]")
    for fs_dir in grouped:
        plex_info = (
            f" [green]({', '.join(fs_dir.plex_shows)})[/green]"
            if fs_dir.plex_shows
            else " [red](NOT TRACKED)[/red]"
        )
        file_display = (
            str(fs_dir.video_files)
            if fs_dir.video_files > 0
            else "files" if fs_dir.has_files else "0"
        )
        branch = tree.add(
            f"{fs_dir.name}/ ({file_display} files, " f"{fs_dir.subdir_count} subdirs){plex_info}"
        )
        for subdir_name in fs_dir.subdirs:
            branch.add(f"[dim]{subdir_name}/[/dim]")

    console.print(tree)


@triage_app.command("fsck-reorganize")
def fsck_reorganize(
    section: str = typer.Option("Anime", help="Library section name to analyze"),
    path_map: str | None = typer.Option(
        None, help="Path mapping from Plex to local, e.g. '/data=/mnt/nfs/media'"
    ),
    risk: Annotated[
        str | None, typer.Option(help="Filter by risk level: low, medium, high")
    ] = None,
) -> None:
    """Generate a reorganization plan to fix Plex parsing issues.

    Analyzes the filesystem and Plex library to propose concrete
    actions (moves, reviews, cleanups) that would resolve grouping
    risks, multi-location merges, and orphan directories.

    No actions are executed automatically — this only produces a plan.
    """
    console.print(f"[bold]Generating reorganization plan for '{section}'...[/bold]")
    pm = _parse_path_map_str(path_map)
    service = _get_fs_service(path_map=pm)
    plan = service.reorganize_plan(section)

    # Summary
    console.print()
    console.print(f"[bold]Reorganization Plan: {plan.section_title}[/bold]")
    console.print(f"  Total proposed actions: {plan.total_actions}")
    console.print()
    for line in plan.summary.split("\n"):
        console.print(f"  {line}")
    console.print()

    # Filter by risk level if requested
    actions = plan.actions
    if risk:
        actions = [a for a in actions if a.risk == risk]

    if not actions:
        console.print("[green]No actions to display.[/green]")
        return

    # Display actions grouped by type
    action_types: dict[str, list[ReorgAction]] = {}
    for a in actions:
        action_types.setdefault(a.action, []).append(a)

    for action_type, type_actions in action_types.items():
        label = {
            "move": "[bold cyan] MOVE PROPOSALS[/bold cyan]",
            "review": "[bold yellow] REVIEW NEEDED[/bold yellow]",
            "remove_empty": "[bold green] CLEANUP[/bold green]",
        }.get(action_type, f"[bold]{action_type.upper()}[/bold]")
        console.print(f"\n{label}")

        table = Table()
        table.add_column("Risk", style="bold", width=6)
        table.add_column("Source", style="cyan")
        table.add_column("Destination", style="green")
        table.add_column("Reason", style="white")

        for a in type_actions:
            risk_marker = f"[{_risk_style(a.risk)}]{a.risk}[/{_risk_style(a.risk)}]"
            dest = a.destination or "-"
            table.add_row(risk_marker, a.source, dest, a.reason)

        console.print(table)

    # Guidance
    console.print("\n[bold]Next Steps:[/bold]")
    console.print(
        "  1. Use [cyan]fix batch-analyze[/cyan] to re-analyze "
        "unanalyzed shows (safest, no filesystem changes)"
    )
    console.print(
        "  2. Review [yellow]'review'[/yellow] actions in your metadata manager "
        "to decide about multi-location merges"
    )
    console.print(
        "  3. Execute [cyan]'move'[/cyan] proposals manually on the "
        "filesystem, then run [cyan]fix scan[/cyan] to update Plex"
    )


# ===================================================================
# PlexMatch commands (generic, no Shoko required)
# ===================================================================


@triage_app.command("plexmatch")
def plexmatch(
    key: Annotated[str | None, typer.Argument(help="Plex rating key for the show")] = None,
    section: Annotated[
        str | None, typer.Option("--section", "-s", help="Library section name")
    ] = None,
    output: Annotated[
        FilePath | None, typer.Option("--output", "-o", help="Write .plexmatch to file")
    ] = None,
    write_to_dir: Annotated[
        str | None,
        typer.Option("--write-to-dir", "-w", help="Write .plexmatch into a show directory"),
    ] = None,
    path_map: Annotated[
        str | None,
        typer.Option(
            "--path-map", help="Path mapping for relative paths (server_path:local_path)"
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
    """Generate a .plexmatch file for a Plex show using metadata only.

    Uses Plex's own metadata (title, year, external IDs) and file paths
    to generate a .plexmatch file — no external metadata source required.

    Use --append with --write-to-dir to preserve existing episode entries in
    an existing .plexmatch file — new entries override duplicates by key.

    Examples:
        plexctl triage plexmatch 12345
        plexctl triage plexmatch 12345 -o .plexmatch
        plexctl triage plexmatch 12345 --write-to-dir /mnt/media/anime/Show
        plexctl triage plexmatch 12345 -w /mnt/media/anime/Show --append
    """
    if key is None:
        console.print("[red]Please provide a Plex rating key.[/red]")
        raise typer.Exit(1)

    service = _get_plexmatch_service()

    # Resolve plexmatch_dir from path_map or write_to_dir
    plexmatch_dir = write_to_dir
    if path_map and not plexmatch_dir:
        # Use the local side of the path mapping
        for mapping in path_map.split(","):
            parts = mapping.split(":", 1)
            if len(parts) == 2:
                plexmatch_dir = parts[1].rstrip("/")
                break

    try:
        result = service.generate_plexmatch(
            key, plexmatch_dir=plexmatch_dir, append=append, append_dir=write_to_dir
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    content = result.render()

    if output:
        output.write_text(content)
        console.print(f"[green]✓[/green] Wrote .plexmatch to {output}")
    elif write_to_dir:
        target = FilePath(write_to_dir) / ".plexmatch"
        target.write_text(content)
        console.print(f"[green]✓[/green] Wrote .plexmatch to {target}")
    else:
        console.print(content)

    console.print(
        f"\n[dim]{result.title}: {len(result.entries)} episodes, "
        f"TMDB={result.tmdb_id or '?'}, TVDB={result.tvdb_id or '?'}, "
        f"IMDb={result.imdb_id or '?'}[/dim]"
    )


@triage_app.command("plexmatch-all")
def plexmatch_all(
    section: Annotated[
        str, typer.Option("--section", "-s", help="Library section name")
    ] = "Anime",
    path_map: Annotated[
        str | None, typer.Option("--path-map", help="Path mapping for relative paths")
    ] = None,
    output_dir: Annotated[
        str | None,
        typer.Option(
            "--output-dir", help="Write .plexmatch files into show directories under this root"
        ),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would be done without writing")
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
    """Generate .plexmatch files for all shows in a section.

    Uses Plex's own metadata — no external metadata source required.

    Use --append to preserve existing episode entries in .plexmatch files —
    new entries override duplicates by season/episode key.

    Examples:
        plexctl triage plexmatch-all -s Anime
        plexctl triage plexmatch-all -s Anime --dry-run
        plexctl triage plexmatch-all -s Anime --output-dir /mnt/media
        plexctl triage plexmatch-all -s Anime --append
    """
    service = _get_plexmatch_service()

    # Resolve plexmatch_dir
    plexmatch_dir = output_dir
    if path_map and not plexmatch_dir:
        for mapping in path_map.split(","):
            parts = mapping.split(":", 1)
            if len(parts) == 2:
                plexmatch_dir = parts[1].rstrip("/")
                break

    result = service.generate_plexmatch_batch(
        section=section, plexmatch_dir=plexmatch_dir, dry_run=dry_run, append=append
    )

    # Display results
    table = Table(title=f"PlexMatch Generation — {section}")
    table.add_column("Key", style="cyan")
    table.add_column("Show", style="white")
    table.add_column("Episodes", justify="right")
    table.add_column("Status")

    for r in result.results:
        status = "[green]✓[/green]" if r.success else f"[red]✗ {r.error}[/red]"
        table.add_row(
            r.show_key or str(r.series_id),
            r.show_name or r.series_name,
            str(r.entry_count),
            status,
        )

    console.print(table)
    console.print(
        f"\n[green]{result.generated}[/green] generated, "
        f"[red]{result.failed}[/red] failed, "
        f"{result.total_dirs} total"
    )


# ===================================================================
# Ingest command (from cli.py)
# ===================================================================


@triage_app.command("ingest")
def ingest(
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
        plexctl triage ingest list
        plexctl triage ingest triage_issue triage_report.csv
    """
    run_ingest(model, file, command_name="triage ingest")


# ===================================================================
# Server commands (from server.py)
# ===================================================================


@triage_app.command("merge")
def merge_items(
    target: str = typer.Argument(help="Rating key of the target item"),
    sources: list[str] = typer.Argument(  # noqa: B008
        help="Rating keys of items to merge into target"
    ),
) -> None:
    """Merge multiple media items into one.

    The target item absorbs all source items. Source items are removed.

    Example:
        plexctl triage merge 12345 67890 54321
    """
    service = _get_server_service()
    result = service.merge(target, list(sources))

    print_result(result, f"Merged {len(sources)} items into {result.key}", "Failed to merge")


@triage_app.command("empty-trash")
def empty_trash(
    section_key: str = typer.Argument(help="Section key (use 'plexctl library list' to find it)"),
) -> None:
    """Empty the trash for a library section.

    Permanently removes all items in the section's trash bin.

    Example:
        plexctl triage empty-trash 2
    """
    service = _get_server_service()
    result = service.empty_trash(section_key)

    print_result(result, f"Emptied trash for section {result.key}", "Failed to empty trash")
