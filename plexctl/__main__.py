"""CLI entry point for plexctl."""

from plexctl.cli import app
from asyncio import run

# __all__ = ["app"]
run(app())
