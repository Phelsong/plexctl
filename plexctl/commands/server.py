"""Server administration and playback commands for plexctl.

Provides commands for:
- Viewing active sessions (who's watching what)
- Rating media items
- Marking items as watched/unwatched
- Emptying section trash
- Deleting items
- Merging media items
- Viewing server info and preferences
- Managing butler (background) tasks
- Watch history and progress management
- On Deck, Recently Added, Continue Watching
- Transcode session listing
"""

import warnings

import typer
from rich.console import Console
from rich.table import Table

from plexctl.client import PlexClient
from plexctl.commands._helpers import if_empty_print, output_csv, print_result, require_confirm
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
from plexctl.options import CsvFlag, OutputFile
from plexctl.services.server import ServerService, parse_duration
from plexctl.services.users import UserService

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

    for session in sessions:
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

    console.print(table)


# --- Rate ------------------------------------------------------------------


@server_app.command(name="rate", deprecated=True)
def rate_item(
    key: str = typer.Argument(help="Plex rating key of the item"),
    rating: float = typer.Argument(help="Rating value (0-10)"),
) -> None:
    """Set the user rating for a media item.

    Example:
        plexctl server rate 12345 8.5
    """
    warnings.warn(
        "Command 'plexctl server rate' is deprecated. Use 'plexctl item rate' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    service = _get_service()
    result = service.rate(key, rating)

    print_result(result, f"Set rating for item {result.key} to {rating}", "Failed to set rating")


# --- Watch state -----------------------------------------------------------


@server_app.command(name="watch", deprecated=True)
def mark_watched(key: str = typer.Argument(help="Plex rating key of the item")) -> None:
    """Mark a media item as watched.

    Example:
        plexctl server watch 12345
    """
    warnings.warn(
        "Command 'plexctl server watch' is deprecated. " "Use 'plexctl item watch' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    service = _get_service()
    result = service.scrobble(key)

    print_result(result, f"Marked item {result.key} as watched", "Failed to mark as watched")


@server_app.command(name="unwatch", deprecated=True)
def mark_unwatched(key: str = typer.Argument(help="Plex rating key of the item")) -> None:
    """Mark a media item as unwatched.

    Example:
        plexctl server unwatch 12345
    """
    warnings.warn(
        "Command 'plexctl server unwatch' is deprecated. " "Use 'plexctl item unwatch' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    service = _get_service()
    result = service.unscrobble(key)

    print_result(result, f"Marked item {result.key} as unwatched", "Failed to mark as unwatched")


# --- Delete -----------------------------------------------------------------


@server_app.command(name="delete", deprecated=True)
def delete_item(
    key: str = typer.Argument(help="Plex rating key of the item to delete"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a media item from the library.

    This permanently removes the item and its metadata.

    Example:
        plexctl server delete 12345 --yes
    """
    warnings.warn(
        "Command 'plexctl server delete' is deprecated. " "Use 'plexctl item delete' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    require_confirm(confirm, f"delete item {key}")

    service = _get_service()
    result = service.delete_item(key)

    print_result(result, f"Deleted item {result.key}", "Failed to delete")


# --- Merge ------------------------------------------------------------------


@server_app.command(name="merge")
def merge_items(
    target: str = typer.Argument(help="Rating key of the target item"),
    sources: list[str] = typer.Argument(  # noqa: B008
        help="Rating keys of items to merge into target"
    ),
) -> None:
    """Merge multiple media items into one.

    The target item absorbs all source items. Source items are removed.

    Example:
        plexctl server merge 12345 67890 54321
    """
    service = _get_service()
    result = service.merge(target, list(sources))

    print_result(result, f"Merged {len(sources)} items into {result.key}", "Failed to merge")


# --- Empty trash -----------------------------------------------------------


@server_app.command(name="empty-trash")
def empty_trash(
    section_key: str = typer.Argument(help="Section key (use 'plexctl library list' to find it)"),
) -> None:
    """Empty the trash for a library section.

    Permanently removes all items in the section's trash bin.

    Example:
        plexctl server empty-trash 2
    """
    service = _get_service()
    result = service.empty_trash(section_key)

    print_result(result, f"Emptied trash for section {result.key}", "Failed to empty trash")


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

    for pref in prefs:
        table.add_row(pref.id, pref.label, str(pref.value), pref.type)

    console.print(table)


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

    for task in tasks:
        enabled_str = "✓" if task.enabled else "✗"
        table.add_row(task.id, task.name, enabled_str, task.schedule)

    console.print(table)


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

    console.print(table)


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


# --- Set progress ----------------------------------------------------------


@server_app.command(name="set-progress", deprecated=True)
def set_progress(
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
        plexctl server set-progress 12345 3600000
        plexctl server set-progress 12345 1800000 --state paused
    """
    service = _get_service()
    result = service.set_progress(rating_key, time_ms, state)

    print_result(
        result,
        f"Set progress for item {result.key} to {time_ms}ms ({state})",
        "Failed to set progress",
    )


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

    for item in items:
        table.add_row(
            item.key,
            item.title or "",
            item.media_type.value if item.media_type else "",
            str(item.year) if item.year else "",
        )

    console.print(table)


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

    for item in items:
        table.add_row(
            item.key,
            item.title or "",
            item.media_type.value if item.media_type else "",
            str(item.year) if item.year else "",
        )

    console.print(table)


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

    for item in items:
        table.add_row(
            item.key,
            item.title or "",
            item.media_type.value if item.media_type else "",
            str(item.year) if item.year else "",
        )

    console.print(table)


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

    console.print(table)


# --- Check for Update -------------------------------------------------------


VALID_TIMESPANS: frozenset[str] = frozenset({"seconds", "hours", "days", "weeks", "months"})


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
def install_update() -> None:
    """Install the latest available Plex Media Server update.

    This will download and apply the update, which may restart the server.
    """
    service = _get_service()

    console.print("[dim]Checking for updates...[/dim]")
    if not service.install_update():
        console.print("[green]✓ Server is already up to date.[/green]")
        return

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
    csv_output: CsvFlag = False,
    output: OutputFile = None,
) -> None:
    """Show server resource utilization (CPU/memory)."""
    service = _get_service()
    stats = service.resource_stats()

    if if_empty_print(stats, "No resource statistics found."):
        return

    if output_csv(stats, resource_stats_to_csv, csv_output, output):
        return

    stats = stats[:limit]

    table = Table(title="Resource Utilization")
    table.add_column("Time", style="cyan")
    table.add_column("Host CPU %", style="green", justify="right")
    table.add_column("Host Memory %", style="yellow", justify="right")
    table.add_column("Process CPU %", style="magenta", justify="right")
    table.add_column("Process Memory %", style="blue", justify="right")

    for stat in stats:
        table.add_row(
            stat.at,
            f"{stat.host_cpu:.1f}",
            f"{stat.host_memory:.1f}",
            f"{stat.process_cpu:.1f}",
            f"{stat.process_memory:.1f}",
        )

    console.print(table)


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

    for user in users:
        table.add_row(
            str(user.id), user.username, user.email, user.title, "✓" if user.friend else "✗"
        )

    console.print(table)

    if typer.confirm("Show user details for each user?"):
        for user in users:
            console.print()
            user_table = user_account_to_table(user)
            console.print(user_table)
