"""Service layer for plexctl."""
from plexctl.services.diagnostics import DiagnosticService
from plexctl.services.fixes import FixService
from plexctl.services.fs_compare import FsCompareService
from plexctl.services.library import LibraryService
from plexctl.services.metadata import MetadataService
from plexctl.services.music import MusicService
from plexctl.services.playlists import PlaylistService, SmartPlaylistService
from plexctl.services.plexmatch import PlexMatchService
from plexctl.services.search import SearchService
from plexctl.services.server import ServerService
from plexctl.services.tree import TreeService
from plexctl.services.triage import TriageService
from plexctl.services.users import UserService

__all__ = [
    "DiagnosticService",
    "FixService",
    "FsCompareService",
    "LibraryService",
    "MetadataService",
    "MusicService",
    "PlexMatchService",
    "PlaylistService",
    "SearchService",
    "ServerService",
    "SmartPlaylistService",
    "TreeService",
    "TriageService",
    "UserService",
]
