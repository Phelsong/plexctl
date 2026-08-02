"""Typer CLI application for plexctl.

Provides subcommands for browsing, reading, and editing Plex metadata.
Supports CSV output via --csv flag and file output via --output flag.
"""

import typer

from plexctl.commands.collections import collections_app
from plexctl.commands.item import item_app
from plexctl.commands.library import library_app
from plexctl.commands.movies import movies_app
from plexctl.commands.music import music_app
from plexctl.commands.photos import photos_app
from plexctl.commands.playlists import playlists_app, smart_app
from plexctl.commands.server import server_app
from plexctl.commands.shows import shows_app
from plexctl.commands.triage import triage_app
from plexctl.plugins.registry import register_plugins
from plexctl.repl import register_help, register_repl
from plexctl.utils.types_helper import types_app

app = typer.Typer(
    name="plexctl",
    help="Plex metadata management toolkit.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

app.add_typer(item_app, name="item")
app.add_typer(library_app, name="library")
app.add_typer(movies_app, name="movies")
app.add_typer(music_app, name="music")
app.add_typer(photos_app, name="photos")
app.add_typer(shows_app, name="shows")
app.add_typer(playlists_app, name="playlists")
app.add_typer(triage_app, name="triage")
app.add_typer(server_app, name="server")
app.add_typer(collections_app, name="collections")
app.add_typer(types_app, name="types")

# Discover and register all plugins (shoko, future integrations, etc.)
register_plugins(app)

# Interactive REPL mode: plexctl repl
register_repl(app)

# plexctl help [cmd] — convenient in the REPL (avoids --help exiting the loop)
register_help(app)

# --- Backward-compat deprecated aliases ---
# Old command groups removed from the active menu in Phase 2E.
# They still work, but Typer marks them [deprecated] in --help output.
# sp → plexctl playlists smart (deprecated top-level alias)
app.add_typer(smart_app, name="sp", deprecated=True)
