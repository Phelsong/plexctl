"""CLI entry point for plexctl."""

from asyncio import run

from plexctl.cli import app

# __all__ = ["app"]
run(app())
