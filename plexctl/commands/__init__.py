"""CLI command modules for plexctl."""

from plexctl.commands.collections import collections_app
from plexctl.commands.item import item_app
from plexctl.commands.library import library_app
from plexctl.commands.movies import movies_app
from plexctl.commands.music import music_app
from plexctl.commands.playlists import playlists_app, smart_app
from plexctl.commands.server import server_app
from plexctl.commands.shows import shows_app
from plexctl.commands.triage import triage_app

__all__ = [
    "collections_app",
    "item_app",
    "library_app",
    "movies_app",
    "music_app",
    "playlists_app",
    "server_app",
    "shows_app",
    "smart_app",
    "triage_app",
]
