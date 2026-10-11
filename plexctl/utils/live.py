"""Live rendering helpers.

Centralizes Rich ``Live`` usage so list commands stream rows into their
tables while data loads (the ``shoko series`` pattern), and monitoring
commands (``server bandwidth``/``resources``) poll on a dashboard until
Ctrl-C.
"""

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.table import Table
from rich.text import Text

TABLE_REFRESH_PER_SECOND = 10
DEFAULT_DASHBOARD_INTERVAL = 5.0


@contextmanager
def stream_table(table: Table, console: Console) -> Iterator[Table]:
    """Render *table* inside a live region while the caller adds rows.

    Usage::

        table = Table(title="...")
        with stream_table(table, console):
            for row in rows:
                table.add_row(...)
    """
    with Live(table, console=console, refresh_per_second=TABLE_REFRESH_PER_SECOND):
        yield table


def poll_dashboard(
    console: Console,
    render: Callable[[], RenderableType],
    interval: float = DEFAULT_DASHBOARD_INTERVAL,
    *,
    add_footer: bool = True,
) -> None:
    """Poll a dashboard until Ctrl-C.

    Calls ``render()`` every *interval* seconds and live-updates the view.
    By default a dim footer with the last-updated timestamp is appended;
    pass ``add_footer=False`` for full-terminal layouts that place their
    own footer inside the frame. A failed fetch renders an error line for
    that cycle instead of aborting.
    """
    try:
        with Live(
            console=console,
            refresh_per_second=4,
            vertical_overflow="crop",  # keep the top; never eat the footer with an ellipsis row
        ) as live:
            while True:
                try:
                    renderable: RenderableType = render()
                except Exception as exc:  # keep the dashboard alive between polls
                    renderable = Text(f"✗ fetch failed: {exc}", style="red")
                if add_footer:
                    renderable = Group(renderable, Text(), _footer(interval))
                live.update(renderable)
                time.sleep(interval)
    except KeyboardInterrupt:
        console.print("[dim]Dashboard stopped.[/dim]")


def _footer(interval: float) -> Text:
    return Text(
        f"updated {time.strftime('%H:%M:%S')} · "
        f"refreshing every {interval:.1f}s · Ctrl-C to exit",
        style="dim",
    )
