"""Music browsing service for plexctl.

Provides high-level operations for listing and exploring music
libraries: artists, albums, and tracks via plexapi.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from plexctl.models import AlbumInfo, ArtistInfo, TrackInfo

if TYPE_CHECKING:
    from plexapi.audio import Album, Artist, Track

    from plexctl.client import PlexClient

logger = logging.getLogger(__name__)


def _extract_tag(value: list | object | None) -> str | None:
    """Extract the first tag string from a genre/country attribute.

    Plexapi returns genres/countries as lists of tag objects with a
    ``.tag`` attribute, or sometimes as a single string. This helper
    normalises both cases.
    """
    if not value:
        return None
    if isinstance(value, list):
        if not value:
            return None
        first = value[0]
        if hasattr(first, "tag"):
            return str(first.tag)
        return str(first)
    return str(value)


class MusicService:
    """Service for Plex music library operations.

    Provides typed, high-level methods for:
    - Listing artists, albums, and tracks
    - Getting details for a single artist, album, or track
    - Fetching recently added music

    Args:
        client: Connected PlexClient instance.
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    def list_artists(
        self, section_title: str = "Music", limit: int | None = None
    ) -> list[ArtistInfo]:
        """List all artists in a music section via plexapi."""
        server = self._client.server
        section = server.library.section(section_title)
        max_results = limit or 9999
        artists = section.search(libtype="artist", limit=max_results)
        return [self._artist_to_info(a) for a in artists]

    def get_artist(self, rating_key: str | int) -> ArtistInfo | None:
        """Get artist details by rating key.

        Returns None if the item is not found or is not an artist.
        """
        server = self._client.server
        item = server.fetchItem(int(rating_key))
        if item and item.type == "artist":
            return self._artist_to_info(item, detailed=True)
        return None

    def list_albums(
        self,
        section_title: str = "Music",
        artist_key: str | int | None = None,
        limit: int | None = None,
    ) -> list[AlbumInfo]:
        """List albums, optionally filtered by artist."""
        server = self._client.server
        if artist_key:
            artist = server.fetchItem(int(artist_key))
            albums = artist.albums()
        else:
            section = server.library.section(section_title)
            max_results = limit or 9999
            albums = section.search(libtype="album", limit=max_results)
        return [self._album_to_info(a) for a in albums]

    def get_album(self, rating_key: str | int) -> AlbumInfo | None:
        """Get album details by rating key.

        Returns None if the item is not found or is not an album.
        """
        server = self._client.server
        item = server.fetchItem(int(rating_key))
        if item and item.type == "album":
            return self._album_to_info(item, detailed=True)
        return None

    def list_tracks(
        self,
        section_title: str = "Music",
        album_key: str | int | None = None,
        artist_key: str | int | None = None,
        limit: int | None = None,
    ) -> list[TrackInfo]:
        """List tracks, optionally filtered by album or artist."""
        server = self._client.server
        if album_key:
            album = server.fetchItem(int(album_key))
            tracks = album.tracks()
        elif artist_key:
            artist = server.fetchItem(int(artist_key))
            tracks = artist.tracks()
        else:
            section = server.library.section(section_title)
            max_results = limit or 9999
            tracks = section.search(libtype="track", limit=max_results)
        return [self._track_to_info(t) for t in tracks]

    def get_track(self, rating_key: str | int) -> TrackInfo | None:
        """Get track details by rating key.

        Returns None if the item is not found or is not a track.
        """
        server = self._client.server
        item = server.fetchItem(int(rating_key))
        if item and item.type == "track":
            return self._track_to_info(item, detailed=True)
        return None

    def recently_added(
        self, section_title: str = "Music", maxresults: int = 50, libtype: str | None = None
    ) -> list[ArtistInfo | AlbumInfo | TrackInfo]:
        """Get recently added music.

        Returns a mixed list that may contain artists, albums, and tracks.
        The libtype filter can restrict to 'artist', 'album', or 'track'.
        """
        server = self._client.server
        section = server.library.section(section_title)
        items = section.recentlyAdded(maxresults=maxresults, libtype=libtype)
        results: list[ArtistInfo | AlbumInfo | TrackInfo] = []
        for item in items:
            if item.type == "artist":
                results.append(self._artist_to_info(item))
            elif item.type == "album":
                results.append(self._album_to_info(item))
            elif item.type == "track":
                results.append(self._track_to_info(item))
        return results

    # --- Private helpers ------------------------------------------------------

    @staticmethod
    def _artist_to_info(artist: Artist, detailed: bool = False) -> ArtistInfo:
        """Convert a plexapi Artist to our ArtistInfo model."""
        genres = getattr(artist, "genres", []) or getattr(artist, "genre", [])
        countries = getattr(artist, "countries", []) or getattr(artist, "country", [])

        info = ArtistInfo(
            key=str(artist.ratingKey),
            title=artist.title or "",
            sort_title=getattr(artist, "titleSort", None),
            summary=artist.summary or None if detailed else None,
            thumb=getattr(artist, "thumb", None),
            art=getattr(artist, "art", None),
            genre=_extract_tag(genres),
            country=_extract_tag(countries),
            album_count=len(artist.albums()) if detailed else 0,
            rating=artist.rating,
            user_rating=getattr(artist, "userRating", None),
        )
        return info

    @staticmethod
    def _album_to_info(album: Album, detailed: bool = False) -> AlbumInfo:
        """Convert a plexapi Album to our AlbumInfo model."""
        genres = getattr(album, "genres", []) or getattr(album, "genre", [])

        parent_key = (
            str(album.parentRatingKey)
            if hasattr(album, "parentRatingKey") and album.parentRatingKey
            else None
        )

        info = AlbumInfo(
            key=str(album.ratingKey),
            title=album.title or "",
            sort_title=getattr(album, "titleSort", None),
            artist=getattr(album, "parentTitle", None),
            artist_key=parent_key,
            year=int(album.year) if album.year else None,
            summary=album.summary or None if detailed else None,
            thumb=getattr(album, "thumb", None),
            genre=_extract_tag(genres),
            studio=getattr(album, "studio", None),
            track_count=len(album.tracks()) if detailed else 0,
            rating=album.rating,
            user_rating=getattr(album, "userRating", None),
            originally_available=getattr(album, "originallyAvailableAt", None),
        )
        return info

    @staticmethod
    def _track_to_info(track: Track, detailed: bool = False) -> TrackInfo:
        """Convert a plexapi Track to our TrackInfo model."""
        genres = getattr(track, "genres", []) or getattr(track, "genre", [])

        grandparent_key = (
            str(track.grandparentRatingKey)
            if hasattr(track, "grandparentRatingKey") and track.grandparentRatingKey
            else None
        )
        parent_key = (
            str(track.parentRatingKey)
            if hasattr(track, "parentRatingKey") and track.parentRatingKey
            else None
        )

        info = TrackInfo(
            key=str(track.ratingKey),
            title=track.title or "",
            sort_title=getattr(track, "titleSort", None),
            artist=getattr(track, "grandparentTitle", None),
            artist_key=grandparent_key,
            album=getattr(track, "parentTitle", None),
            album_key=parent_key,
            track_number=getattr(track, "index", None),
            disc_number=getattr(track, "parentIndex", None),
            duration=(int(track.duration) if track.duration else None),
            year=int(track.year) if track.year else None,
            genre=_extract_tag(genres),
            rating=track.rating,
            user_rating=getattr(track, "userRating", None),
            view_count=getattr(track, "viewCount", 0) or 0,
        )
        return info
