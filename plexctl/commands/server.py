"""Server administration and playback commands for plexctl.

Provides commands for:
- Viewing active sessions (who's watching what)
- Viewing server info and preferences
- Managing butler (background) tasks
- Watch history and progress management
- On Deck, Recently Added, Continue Watching
- Transcode session listing
"""

import time

import typer
from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import ProgressBar  # type: ignore[attr-defined]
from rich.table import Table
from rich.text import Text

from plexctl.client import PlexClient
from plexctl.commands._helpers import if_empty_print, output_csv, print_result
from plexctl.config import load_config
from plexctl.converters import (
    bandwidth_stats_to_csv,
    butler_task_to_csv,
    media_metadata_to_csv,
    playback_session_to_csv,
    resource_stats_to_csv,
    server_info_to_csv,
    server_preference_to_csv,
    transcode_session_to_csv,
    update_info_to_csv,
    user_account_to_table,
    watch_history_entry_to_csv,
)
from plexctl.models import PlaybackSession, ResourceStats
from plexctl.options import CsvFlag, OutputFile
from plexctl.services.server import ServerService, parse_duration
from plexctl.services.users import UserService
from plexctl.utils.live import (
    DEFAULT_DASHBOARD_INTERVAL,
    poll_dashboard,
    stream_table,
)

server_app = typer.Typer(
    name="server", help="Plex server administration and playback commands.", no_args_is_help=True
)
console = Console()


def _get_service() -> ServerService:
    """Load config and create a connected ServerService."""
    config = load_config()
    client = PlexClient(config)
    return ServerService(client)


# --- Sessions --------------------------------------------------------------


@server_app.command(name="sessions")
def list_sessions(csv_output: CsvFlag = False, output: OutputFile = None) -> None:
    """List active playback sessions on the server."""
    service = _get_service()
    sessions = service.list_sessions()

    if if_empty_print(sessions, "No active playback sessions."):
        return

    if output_csv(sessions, playback_session_to_csv, csv_output, output):
        return

    table = Table(title="Active Sessions")
    table.add_column("Key", style="cyan")
    table.add_column("User", style="green")
    table.add_column("Player", style="yellow")
    table.add_column("State", style="magenta")
    table.add_column("Title", style="white")
    table.add_column("Type", style="blue")
    table.add_column("Transcode", style="red")

    with stream_table(table, console):
        for session in sessions:
            _add_session_row(table, session)


def _add_session_row(table: Table, session: PlaybackSession) -> None:
    """Add one playback session row to a Rich table."""
    # For episodes, show "Show - Season X - Episode"
    display_title = session.title
    if session.grandparent_title:
        display_title = f"{session.grandparent_title} - {display_title}"

    state_color = {
        "playing": "[green]playing[/green]",
        "paused": "[yellow]paused[/yellow]",
        "buffering": "[blue]buffering[/blue]",
    }.get(session.state, session.state)

    table.add_row(
        session.rating_key,
        session.user,
        session.player_title,
        state_color,
        display_title,
        session.media_type,
        "✓" if session.transcoding else "",
    )


# --- Server Info ------------------------------------------------------------


@server_app.command(name="info")
def server_info(csv_output: CsvFlag = False, output: OutputFile = None) -> None:
    """Display Plex server identity and version information."""
    service = _get_service()
    info = service.server_info()

    if output_csv([info], server_info_to_csv, csv_output, output):
        return

    console.print("\n[bold]Plex Media Server[/bold]")
    console.print(f"  Name:        {info.server_name}")
    console.print(f"  Version:     {info.version}")
    console.print(f"  Platform:    {info.platform} {info.platform_version}")
    console.print(f"  Machine ID:  {info.machine_id}")
    if info.owner:
        console.print(f"  Owner:       {info.owner}")
    console.print()


# --- Preferences -----------------------------------------------------------


@server_app.command(name="prefs")
def list_prefs(csv_output: CsvFlag = False, output: OutputFile = None) -> None:
    """List Plex server preference settings."""
    service = _get_service()
    prefs = service.list_preferences()

    if if_empty_print(prefs, "No preferences found."):
        return

    if output_csv(prefs, server_preference_to_csv, csv_output, output):
        return

    table = Table(title="Server Preferences")
    table.add_column("ID", style="cyan", max_width=30)
    table.add_column("Label", style="green")
    table.add_column("Value", style="yellow")
    table.add_column("Type", style="magenta")

    with stream_table(table, console):
        for pref in prefs:
            table.add_row(pref.id, pref.label, str(pref.value), pref.type)


@server_app.command(name="set-pref")
def set_pref(
    pref_id: str = typer.Argument(help="Preference key name"),
    value: str = typer.Argument(help="New value for the preference"),
) -> None:
    """Set a server preference value.

    Example:
        plexctl server set-pref FriendlyName "My Plex Server"
    """
    service = _get_service()
    result = service.set_preference(pref_id, value)

    print_result(result, f"Set {pref_id} = {value}", "Failed to set preference")


# --- Butler tasks ----------------------------------------------------------


@server_app.command(name="butler")
def list_butler_tasks(csv_output: CsvFlag = False, output: OutputFile = None) -> None:
    """List all butler (background maintenance) tasks."""
    service = _get_service()
    tasks = service.list_butler_tasks()

    if if_empty_print(tasks, "No butler tasks found."):
        return

    if output_csv(tasks, butler_task_to_csv, csv_output, output):
        return

    table = Table(title="Butler Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Enabled", style="yellow")
    table.add_column("Schedule", style="magenta")

    with stream_table(table, console):
        for task in tasks:
            enabled_str = "✓" if task.enabled else "✗"
            table.add_row(task.id, task.name, enabled_str, task.schedule)


@server_app.command(name="butler-run")
def run_butler_task(
    task_name: str = typer.Argument(help="Name/key of the butler task to run"),
) -> None:
    """Run a butler task immediately.

    Example:
        plexctl server butler-run CleanOldBundles
    """
    service = _get_service()
    result = service.run_butler_task(task_name)

    print_result(result, f"Started butler task: {task_name}", "Failed to start butler task")


# --- Watch history ---------------------------------------------------------


@server_app.command(name="history")
def watch_history(
    maxresults: int | None = typer.Option(
        None, "--maxresults", "-n", help="Maximum history entries to return."
    ),
    mindate: str | None = typer.Option(
        None,
        "--mindate",
        help="Only show items viewed after this date (e.g. '7d', '1h', '30m', '1w').",
    ),
    key: int | None = typer.Option(None, "--key", help="Filter to a specific rating key."),
    account: int | None = typer.Option(
        None, "--account", help="Filter to a specific Plex account ID."
    ),
    section: int | None = typer.Option(
        None, "--section", help="Filter to a specific library section ID."
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Display watch history for the server.

    Example:
        plexctl server history --mindate 7d
        plexctl server history --maxresults 50 --key 12345
        plexctl server history --account 1 --section 2
    """
    service = _get_service()

    parsed_mindate = None
    if mindate:
        try:
            parsed_mindate = parse_duration(mindate)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

    entries = service.history(
        maxresults=maxresults,
        mindate=parsed_mindate,
        rating_key=key,
        account_id=account,
        section_id=section,
    )

    if if_empty_print(entries, "No watch history found."):
        return

    if output_csv(entries, watch_history_entry_to_csv, csv_output, output):
        return

    table = Table(title="Watch History")
    table.add_column("Key", style="cyan", max_width=10)
    table.add_column("Title", style="white")
    table.add_column("Type", style="blue")
    table.add_column("Year", style="yellow", max_width=6)
    table.add_column("Viewed At", style="green")
    table.add_column("Show/Artist", style="magenta")

    with stream_table(table, console):
        for entry in entries:
            grandparent = entry.grandparent_title or ""
            table.add_row(
                entry.key,
                entry.title,
                entry.media_type,
                str(entry.year) if entry.year else "",
                entry.viewed_at or "",
                grandparent,
            )


# --- Stop session ----------------------------------------------------------


@server_app.command(name="stop-session")
def stop_session(
    session_key: str = typer.Argument(
        help="Session key to stop (from 'plexctl server sessions')."
    ),
    reason: str = typer.Option("", "--reason", help="Reason for stopping the session."),
) -> None:
    """Stop an active playback session.

    Example:
        plexctl server stop-session abc123
        plexctl server stop-session abc123 --reason "Maintenance"
    """
    service = _get_service()
    result = service.stop_session(session_key, reason)

    print_result(result, f"Stopped session {session_key}", "Failed to stop session")


# --- On Deck ---------------------------------------------------------------


@server_app.command(name="on-deck")
def on_deck(
    section: int | None = typer.Option(
        None, "-s", "--section", help="Library section key to scope results."
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum number of items to display."),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Show On Deck items.

    Example:
        plexctl server on-deck
        plexctl server on-deck -s 2
        plexctl server on-deck --limit 20
    """
    service = _get_service()
    items = service.on_deck(section_key=section)

    if if_empty_print(items, "No On Deck items."):
        return

    if output_csv(items, media_metadata_to_csv, csv_output, output):
        return

    items = items[:limit]

    table = Table(title="On Deck")
    table.add_column("Key", style="cyan", max_width=10)
    table.add_column("Title", style="white")
    table.add_column("Type", style="blue")
    table.add_column("Year", style="yellow", max_width=6)

    with stream_table(table, console):
        for item in items:
            table.add_row(
                item.key,
                item.title or "",
                item.media_type.value if item.media_type else "",
                str(item.year) if item.year else "",
            )


# --- Recently Added --------------------------------------------------------


@server_app.command(name="recently-added")
def recently_added(
    section: int | None = typer.Option(
        None, "-s", "--section", help="Library section key to scope results."
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum number of items to return."),
    type: str | None = typer.Option(
        None, "--type", help="Library type filter (e.g. 'movie', 'episode')."
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Show recently added items.

    Example:
        plexctl server recently-added
        plexctl server recently-added -s 2 --limit 20
        plexctl server recently-added --type movie
    """
    service = _get_service()
    items = service.recently_added(section_key=section, maxresults=limit, libtype=type)

    if if_empty_print(items, "No recently added items."):
        return

    if output_csv(items, media_metadata_to_csv, csv_output, output):
        return

    table = Table(title="Recently Added")
    table.add_column("Key", style="cyan", max_width=10)
    table.add_column("Title", style="white")
    table.add_column("Type", style="blue")
    table.add_column("Year", style="yellow", max_width=6)

    with stream_table(table, console):
        for item in items:
            table.add_row(
                item.key,
                item.title or "",
                item.media_type.value if item.media_type else "",
                str(item.year) if item.year else "",
            )


# --- Continue Watching -----------------------------------------------------


@server_app.command(name="continue-watching")
def continue_watching(
    section: int | None = typer.Option(
        None, "-s", "--section", help="Library section key to scope results."
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum number of items to display."),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Show Continue Watching items.

    Example:
        plexctl server continue-watching
        plexctl server continue-watching -s 2
        plexctl server continue-watching --limit 20
    """
    service = _get_service()
    items = service.continue_watching(section_key=section)

    if if_empty_print(items, "No Continue Watching items."):
        return

    if output_csv(items, media_metadata_to_csv, csv_output, output):
        return

    items = items[:limit]

    table = Table(title="Continue Watching")
    table.add_column("Key", style="cyan", max_width=10)
    table.add_column("Title", style="white")
    table.add_column("Type", style="blue")
    table.add_column("Year", style="yellow", max_width=6)

    with stream_table(table, console):
        for item in items:
            table.add_row(
                item.key,
                item.title or "",
                item.media_type.value if item.media_type else "",
                str(item.year) if item.year else "",
            )


# --- Transcode sessions ----------------------------------------------------


@server_app.command(name="get-transcodes")
def list_transcode_sessions(csv_output: CsvFlag = False, output: OutputFile = None) -> None:
    """List active transcode sessions.

    Example:
        plexctl server get-transcodes
        plexctl server get-transcodes --csv
    """
    service = _get_service()
    sessions = service.transcode_sessions()

    if if_empty_print(sessions, "No active transcode sessions."):
        return

    if output_csv(sessions, transcode_session_to_csv, csv_output, output):
        return

    table = Table(title="Transcode Sessions")
    table.add_column("Key", style="cyan", max_width=12)
    table.add_column("Progress", style="green")
    table.add_column("Speed", style="yellow")
    table.add_column("Throttled", style="red")
    table.add_column("Video Decision", style="blue")
    table.add_column("Audio Decision", style="blue")
    table.add_column("Context", style="magenta")

    with stream_table(table, console):
        for session in sessions:
            throttled_str = "✓" if session.throttled else ""
            table.add_row(
                session.key,
                f"{session.progress:.1f}%",
                f"{session.speed:.2f}x",
                throttled_str,
                session.video_decision,
                session.audio_decision,
                session.context,
            )


# --- Check for Update -------------------------------------------------------


VALID_TIMESPANS: frozenset[str] = frozenset({"seconds", "hours", "days", "weeks", "months"})

# Rows reserved for the bars view (4 bar rows), history table
# frame/header (title, borders, column header), footer, plus a safety
# margin because terminals frequently expose one or two fewer usable rows
# than they report. The latest entry's timestamp is the last history row,
# so no separate label is rendered.
RESOURCES_DASHBOARD_CHROME_ROWS = 12


@server_app.command(name="check-update")
def check_for_update(csv_output: CsvFlag = False, output: OutputFile = None) -> None:
    """Check for available Plex Media Server updates."""
    service = _get_service()
    info = service.check_for_update()

    if info is None:
        console.print("[green]✓ Server is up to date.[/green]")
        return

    if output_csv([info], update_info_to_csv, csv_output, output):
        return

    console.print("\n[bold]Update Available[/bold]")
    console.print(f"  Version:       {info.version}")
    console.print(f"  State:          {info.state}")
    console.print(f"  Download URL:  {info.download_url}")

    if info.added:
        console.print("\n  [bold]Added:[/bold]")
        console.print(f"    {info.added}")
    if info.fixed:
        console.print("\n  [bold]Fixed:[/bold]")
        console.print(f"    {info.fixed}")
    if info.release_notes:
        console.print("\n  [bold]Release Notes:[/bold]")
        console.print(f"    {info.release_notes}")
    console.print()


# --- Install Update --------------------------------------------------------


@server_app.command(name="install-update")
def install_update(
    tonight: bool = typer.Option(
        False,
        "--tonight",
        help=(
            "Schedule the update to install during the server's next "
            "maintenance window tonight. Takes precedence over --skip."
        ),
    ),
    skip: bool = typer.Option(
        False,
        "--skip",
        help="Skip this update and wait for the next one. Ignored if --tonight is set.",
    ),
) -> None:
    """Install the latest available Plex Media Server update.

    Downloads the update if needed, then applies it. The server may
    restart to apply the update. Use --tonight to defer the install to
    the server's maintenance window, or --skip to dismiss this update.
    """
    service = _get_service()

    console.print("[dim]Checking and Downloading updates... This may take several minutes.[/dim]")
    try:
        applied = service.install_update(tonight=tonight, skip=skip)
    except ValueError as exc:
        console.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(code=1) from None

    if not applied:
        console.print("[green]✓ Server is already up to date.[/green]")
        return

    if tonight:
        console.print("[green]✓ Update scheduled for tonight's maintenance window.[/green]")
    elif skip:
        console.print(
            "[green]✓ Update skipped. The server will wait for the next release.[/green]"
        )
    else:
        console.print("[green]✓ Update installed successfully.[/green]")
        console.print("[dim]The server may restart to apply the update.[/dim]")


# --- Bandwidth statistics --------------------------------------------------


@server_app.command(name="bandwidth")
def bandwidth_stats(
    timespan: str = typer.Option(
        "hours", "--timespan", "-t", help="Time granularity: seconds, hours, days, weeks, months"
    ),
    account: int | None = typer.Option(None, "--account", help="Filter by account ID."),
    device: int | None = typer.Option(None, "--device", help="Filter by device ID."),
    lan: bool | None = typer.Option(None, "--lan/--remote", help="Local only or remote only."),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of entries to display."),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Show server bandwidth statistics."""
    normalized = timespan.lower()
    if normalized not in VALID_TIMESPANS:
        valid = ", ".join(sorted(VALID_TIMESPANS))
        console.print(f"[red]Invalid timespan '{timespan}'. Use: {valid}[/red]")
        raise typer.Exit(code=1)

    service = _get_service()
    stats = service.bandwidth_stats(
        timespan=normalized, account_id=account, device_id=device, lan=lan
    )

    if if_empty_print(stats, "No bandwidth statistics found."):
        return

    if output_csv(stats, bandwidth_stats_to_csv, csv_output, output):
        return

    stats = stats[:limit]

    timespan_label = normalized.capitalize()
    table = Table(title=f"Bandwidth Statistics ({timespan_label})")
    table.add_column("Time", style="cyan")
    table.add_column("Bytes", style="green", justify="right")
    table.add_column("LAN", style="yellow")
    table.add_column("Account ID", style="magenta")
    table.add_column("Device ID", style="blue")

    for stat in stats:
        lan_str = "✓" if stat.lan else ""
        acct_str = str(stat.account_id) if stat.account_id is not None else ""
        dev_str = str(stat.device_id) if stat.device_id is not None else ""
        table.add_row(stat.at, f"{stat.bytes:,}", lan_str, acct_str, dev_str)

    console.print(table)


# --- Resource statistics ---------------------------------------------------


@server_app.command(name="resources")
def resource_stats(
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of entries to display."),
    interval: float = typer.Option(
        DEFAULT_DASHBOARD_INTERVAL,
        "--interval",
        "-i",
        help="Seconds between dashboard refreshes.",
    ),
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Show server resource utilization (CPU/memory).

    Displays a live dashboard that re-polls the server every --interval
    seconds until Ctrl-C: the historic utilization table is listed above
    and progress bars for the latest result sit below it. Use --csv to
    dump a single snapshot instead.
    """
    service = _get_service()
    stats = service.resource_stats()

    if if_empty_print(stats, "No resource statistics found."):
        return

    if output_csv(stats, resource_stats_to_csv, csv_output, output):
        return

    def render() -> Group:
        stats = service.resource_stats()[:limit]

        # Keep the most recent rows that fit above the bars panel + footer.
        max_rows = max(3, console.size.height - RESOURCES_DASHBOARD_CHROME_ROWS)
        shown = stats[-max_rows:]

        table = Table(
            title=(
                "Resource Utilization"
                if len(shown) == len(stats)
                else f"Resource Utilization (latest {len(shown)} of {len(stats)})"
            )
        )
        table.add_column("Time", style="cyan")
        table.add_column("Host CPU %", style="green", justify="right")
        table.add_column("Host Memory %", style="yellow", justify="right")
        table.add_column("Process CPU %", style="magenta", justify="right")
        table.add_column("Process Memory %", style="blue", justify="right")

        for stat in shown:
            table.add_row(
                stat.at,
                f"{stat.host_cpu:.1f}",
                f"{stat.host_memory:.1f}",
                f"{stat.process_cpu:.1f}",
                f"{stat.process_memory:.1f}",
            )

        latest = shown[-1]
        return Group(table, _resource_bars(latest))

    poll_dashboard(console, render, interval=interval)


# --- Live dashboard ---------------------------------------------------------


@server_app.command(name="dashboard")
def live_dashboard(
    interval: float = typer.Option(
        DEFAULT_DASHBOARD_INTERVAL,
        "--interval",
        "-i",
        help="Seconds between dashboard refreshes.",
    ),
) -> None:
    """Live combined dashboard: active streams plus server resources.

    Renders in a full-terminal frame that re-polls active playback
    sessions and CPU/memory utilization every --interval seconds until
    Ctrl-C.
    """
    service = _get_service()

    def render() -> Layout:
        sessions = service.list_sessions()
        stats = service.resource_stats()

        if sessions:
            streams_view: RenderableType = _build_streams_table(sessions)
        else:
            streams_view = Text("No active playback sessions.", justify="center", style="dim")

        if stats:
            resources_view: RenderableType = _resource_bars(stats[-1])
        else:
            resources_view = Text("No resource statistics found.", justify="center", style="dim")

        footer = Text(
            f"updated {time.strftime('%H:%M:%S')} · "
            f"refreshing every {interval:.1f}s · Ctrl-C to exit",
            style="dim",
            justify="right",
        )

        # Bars block is 4 rows (+2 panel borders); text fallback is 1 (+2).
        lower_region = Layout(
            Panel(resources_view, title="Server Resources", border_style="dim"),
            name="resources",
            size=6 if stats else 3,
        )

        layout = Layout(name="root")
        layout.split_column(
            Layout(
                Panel(
                    streams_view,
                    title=f"Active Streams ({len(sessions)})",
                    border_style="dim",
                ),
                name="streams",
            ),
            lower_region,
            Layout(footer, name="footer", size=1),
        )
        return layout

    poll_dashboard(console, render, interval=interval, add_footer=False)


def _build_streams_table(sessions: list[PlaybackSession]) -> Table:
    """Build the active-streams table (all active sessions, newest last)."""
    streams_table = Table()
    streams_table.add_column("Key", style="cyan")
    streams_table.add_column("User", style="green")
    streams_table.add_column("Player", style="yellow")
    streams_table.add_column("State", style="magenta")
    streams_table.add_column("Title", style="white")
    streams_table.add_column("Type", style="blue")
    streams_table.add_column("Transcode", style="red")
    for session in sessions:
        _add_session_row(streams_table, session)
    return streams_table


def _resource_bars(stat: ResourceStats) -> Table:
    """Build a borderless table of progress bars for a ResourceStats entry."""
    metrics = [
        ("Host CPU", stat.host_cpu, "green"),
        ("Host Memory", stat.host_memory, "yellow"),
        ("Process CPU", stat.process_cpu, "magenta"),
        ("Process Memory", stat.process_memory, "blue"),
    ]

    bars = Table(show_header=False, box=None, padding=(0, 2))
    bars.add_column(justify="right", min_width=15)
    bars.add_column(ratio=1)
    bars.add_column(justify="right", min_width=6)

    for label, value, style in metrics:
        bars.add_row(
            Text(label, style=style),
            ProgressBar(
                total=100.0,
                completed=min(value, 100.0),
                complete_style=style,
                finished_style=style,
            ),
            Text(f"{value:.1f}%", style="bold " + style),
        )

    return bars


# --- Download logs ---------------------------------------------------------


@server_app.command(name="download-logs")
def download_logs(
    savepath: str | None = typer.Option(None, "--path", "-p", help="Directory to save logs."),
    unpack: bool = typer.Option(False, "--unpack", help="Unpack the zip file."),
) -> None:
    """Download Plex Media Server logs."""
    service = _get_service()

    try:
        result = service.download_logs(savepath=savepath, unpack=unpack)
        console.print(f"[green]✓ Logs downloaded to: {result}[/green]")
    except Exception as exc:
        console.print(f"[red]✗ Failed to download logs: {exc}[/red]")
        raise typer.Exit(code=1) from exc


# --- Download databases ----------------------------------------------------


@server_app.command(name="download-dbs")
def download_databases(
    savepath: str | None = typer.Option(
        None, "--path", "-p", help="Directory to save databases."
    ),
    unpack: bool = typer.Option(False, "--unpack", help="Unpack the zip file."),
) -> None:
    """Download Plex Media Server databases for backup."""
    service = _get_service()

    try:
        result = service.download_databases(savepath=savepath, unpack=unpack)
        console.print(f"[green]✓ Databases downloaded to: {result}[/green]")
    except Exception as exc:
        console.print(f"[red]✗ Failed to download databases: {exc}[/red]")
        raise typer.Exit(code=1) from exc


@server_app.command(name="accounts")
def list_accounts(
    media_key: int | None = typer.Option(
        None, "--media", "-m", help="Rating key of media item to find users."
    )
) -> None:
    """List Plex account users.

    If --media is provided, shows users who have played the item.
    Otherwise shows account information from the Plex API.
    """
    if media_key:
        service = UserService(_get_service()._client)
        users = service.media_users(media_key)
    else:
        # List known user accounts from server
        console.print(
            "[yellow]Note: Full account list endpoint requires authentication.[/yellow]"
        )
        console.print(
            "[yellow]Use --media with a rating key to find "
            "users who interacted with items.[/yellow]"
        )
        return

    if if_empty_print(users, "No users found for this media."):
        return

    table = Table(title="Users")
    table.add_column("ID", style="cyan")
    table.add_column("Username", style="green")
    table.add_column("Email", style="blue")
    table.add_column("Title", style="yellow")
    table.add_column("Friend", style="magenta")

    with stream_table(table, console):
        for user in users:
            table.add_row(
                str(user.id), user.username, user.email, user.title, "✓" if user.friend else "✗"
            )

    if typer.confirm("Show user details for each user?"):
        for user in users:
            console.print()
            user_table = user_account_to_table(user)
            console.print(user_table)
