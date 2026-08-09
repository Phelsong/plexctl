"""types helper"""

import typer
from rich.console import Console

from plexctl.models import MediaType, MetadataType

types_app = typer.Typer(name="types", help="get plex types")
console = Console()


@types_app.command(name="types")
def print_types() -> None:
    """print reference types to the console"""
    for x in MediaType:
        console.print(f"[green]{x}[/green]")
    for y in MetadataType:
        console.print(f"[green]{y.name}, {y}[/green]")
