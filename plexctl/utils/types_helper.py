"""types helper"""

from rich.console import Console
from rich.live import Live
from rich.table import Table
from typer import Typer

from plexctl.models import MediaType, MetadataType

types_app = Typer(name="types", help="get plex types", no_args_is_help=True)
console = Console()


@types_app.command(name="list")
def print_types() -> None:
    """print reference types to the console"""
    console.print("")
    types_table = Table(title="Media Types")
    types_table.add_column("Name", style="cyan", justify="center")
    types_table.add_column("Id", style="cyan", justify="center")

    with Live(types_table, console=console, refresh_per_second=10):
        for x in MediaType:
            # from contextlib import suppress
            # with suppress(KeyError):
            try:
                types_table.add_row(f"{x}", f"{MetadataType[x]}", style="cyan")
            except KeyError:
                types_table.add_row(f"{x}", "", style="cyan")
