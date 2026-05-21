"""Photo service layer.

Provides high-level operations for browsing Plex photo libraries:
- Listing photo albums in a section
- Retrieving album details
- Listing photos (optionally filtered by album)
- Retrieving photo details
- Recently added photo albums

Uses PlexClient.server for plexapi interactions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from plexctl.models import PhotoAlbumInfo, PhotoInfo

if TYPE_CHECKING:
    from plexctl.client import PlexClient

logger = logging.getLogger(__name__)


class PhotoService:
    """Service for Plex photo library operations.

    Args:
        client: Connected PlexClient instance.
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    def list_albums(
        self, section_title: str = "Photos", limit: int | None = None
    ) -> list[PhotoAlbumInfo]:
        """List all photo albums in a section.

        Args:
            section_title: Library section name (default "Photos").
            limit: Maximum number of albums to return.

        Returns:
            List of PhotoAlbumInfo for each album in the section.
        """
        server = self._client.server
        section = server.library.section(section_title)
        albums = section.all(libtype="photoalbum", limit=limit or 9999)
        return [self._album_to_info(a) for a in albums]

    def get_album(self, rating_key: str | int) -> PhotoAlbumInfo | None:
        """Get album details by rating key.

        Args:
            rating_key: Plex rating key for the album.

        Returns:
            PhotoAlbumInfo if found, None otherwise.
        """
        server = self._client.server
        item = server.fetchItem(int(rating_key))
        if item is None:
            return None
        # plexapi photo albums have type='photoalbum'
        item_type = getattr(item, "type", None)
        if item_type != "photoalbum":
            return None
        return self._album_to_info(item, detailed=True)

    def list_photos(
        self,
        section_title: str = "Photos",
        album_key: str | int | None = None,
        limit: int | None = None,
    ) -> list[PhotoInfo]:
        """List photos, optionally filtered by album.

        Args:
            section_title: Library section name (default "Photos").
            album_key: Optional rating key of a photo album to filter by.
            limit: Maximum number of photos to return.

        Returns:
            List of PhotoInfo for each matching photo.
        """
        server = self._client.server
        if album_key is not None:
            album = server.fetchItem(int(album_key))
            photos = album.photos()
        else:
            section = server.library.section(section_title)
            photos = section.search(libtype="photo", limit=limit or 9999)
        return [self._photo_to_info(p) for p in photos]

    def get_photo(self, rating_key: str | int) -> PhotoInfo | None:
        """Get photo details by rating key.

        Args:
            rating_key: Plex rating key for the photo.

        Returns:
            PhotoInfo if found, None otherwise.
        """
        server = self._client.server
        item = server.fetchItem(int(rating_key))
        if item is None:
            return None
        item_type = getattr(item, "type", None)
        if item_type != "photo":
            return None
        return self._photo_to_info(item, detailed=True)

    def recently_added(
        self, section_title: str = "Photos", maxresults: int = 50
    ) -> list[PhotoAlbumInfo]:
        """Get recently added photo albums.

        Args:
            section_title: Library section name (default "Photos").
            maxresults: Maximum number of albums to return.

        Returns:
            List of PhotoAlbumInfo for recently added albums.
        """
        server = self._client.server
        section = server.library.section(section_title)
        albums = section.recentlyAddedAlbums(maxresults=maxresults)
        return [self._album_to_info(a) for a in albums]

    # --- Private helpers ---------------------------------------------------

    @staticmethod
    def _album_to_info(album: object, detailed: bool = False) -> PhotoAlbumInfo:
        """Convert a plexapi Photoalbum to PhotoAlbumInfo model.

        Args:
            album: plexapi Photoalbum object.
            detailed: Whether to include extra detail fields.

        Returns:
            PhotoAlbumInfo with album metadata.
        """
        summary = None
        if detailed:
            summary = getattr(album, "summary", None) or None

        thumb = getattr(album, "thumb", None)
        if thumb and not isinstance(thumb, str):
            thumb = None

        return PhotoAlbumInfo(
            key=str(album.ratingKey),  # type: ignore[attr-defined]
            title=album.title,  # type: ignore[attr-defined]
            sort_title=getattr(album, "titleSort", None),
            summary=summary,
            thumb=thumb,
            photo_count=_safe_count(album),
            user_rating=getattr(album, "userRating", None),
        )

    @staticmethod
    def _photo_to_info(photo: object, detailed: bool = False) -> PhotoInfo:
        """Convert a plexapi Photo to PhotoInfo model.

        Args:
            photo: plexapi Photo object.
            detailed: Whether to include extra detail fields.

        Returns:
            PhotoInfo with photo metadata.
        """
        album_name = None
        album_key = None

        if detailed:
            try:
                parent = photo.photoalbum()  # type: ignore[attr-defined]
                if parent is not None:
                    album_name = getattr(parent, "title", None)
                    parent_key = getattr(parent, "ratingKey", None)
                    if parent_key is not None:
                        album_key = str(parent_key)
            except Exception:
                logger.debug(
                    "Could not resolve parent album for photo %s",
                    getattr(photo, "ratingKey", "?"),
                )

        thumb = getattr(photo, "thumb", None)
        if thumb and not isinstance(thumb, str):
            thumb = None

        orig_available = getattr(photo, "originallyAvailableAt", None)
        if orig_available is not None:
            orig_available = str(orig_available)

        tags = None
        if detailed:
            # Collect tag labels if available
            tag_list = getattr(photo, "moods", [])
            if tag_list:
                tags = "|".join(
                    getattr(t, "tag", str(t)) if hasattr(t, "tag") else str(t) for t in tag_list
                )

        return PhotoInfo(
            key=str(photo.ratingKey),  # type: ignore[attr-defined]
            title=photo.title,  # type: ignore[attr-defined]
            sort_title=getattr(photo, "titleSort", None),
            album=album_name,
            album_key=album_key,
            originally_available=orig_available,
            thumb=thumb,
            user_rating=getattr(photo, "userRating", None),
            year=_safe_int(getattr(photo, "year", None)),
            tags=tags,
        )


def _safe_int(value: object) -> int | None:
    """Safely convert a value to int, returning None for missing/empty values."""
    if value is None or value == "":
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


def _safe_count(album: object) -> int:
    """Extract photo count from a plexapi album object.

    plexapi albums may expose childCount, leafCount, or neither.
    Try childCount first (direct property), then leafCount.
    """
    child_count = getattr(album, "childCount", None)
    if child_count is not None:
        try:
            return int(child_count)
        except (ValueError, TypeError):
            pass
    leaf_count = getattr(album, "leafCount", None)
    if leaf_count is not None:
        try:
            return int(leaf_count)
        except (ValueError, TypeError):
            pass
    return 0
