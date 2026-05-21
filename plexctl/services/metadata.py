"""Metadata service layer.

Provides high-level operations for reading and writing Plex metadata,
collections, and library information. All plexapi interactions are
encapsulated here so the CLI layer stays thin.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from plexapi.video import Episode, Movie, Season, Show

if TYPE_CHECKING:
    from collections.abc import Generator

    from plexctl.client import PlexClient

from plexctl.models import (
    BatchEditResult,
    CollectionInfo,
    LibrarySection,
    MediaMetadata,
    MediaType,
    MetadataEdit,
    SubtitleStreamInfo,
)

# Maps tag_type strings to the corresponding plexapi method names.
_TAG_ADD_METHODS: dict[str, str] = {
    "genre": "addGenre",
    "collection": "addCollection",
    "label": "addLabel",
    "director": "addDirector",
    "writer": "addWriter",
    "mood": "addMood",
    "style": "addStyle",
    "country": "addCountry",
    "similar_artist": "addSimilarArtist",
}

_TAG_REMOVE_METHODS: dict[str, str] = {
    "genre": "removeGenre",
    "collection": "removeCollection",
    "label": "removeLabel",
    "director": "removeDirector",
    "writer": "removeWriter",
    "mood": "removeMood",
    "style": "removeStyle",
    "country": "removeCountry",
    "similar_artist": "removeSimilarArtist",
}

logger = logging.getLogger(__name__)


@contextmanager
def _batch_edits(item: Movie | Show) -> Generator[None, None, None]:
    """Context manager that applies edits in a single batch on exit."""
    try:
        with item.batchEdits():  # type: ignore[no-untyped-call]
            yield
    except Exception:
        logger.exception("Batch edit failed for %s", item.title)
        raise


class MetadataService:
    """Service for Plex metadata operations.

    Provides typed, high-level methods for:
    - Browsing libraries and sections
    - Reading metadata for movies and shows
    - Editing metadata (titles, summaries, ratings, etc.)
    - Managing collections

    Args:
        client: Connected PlexClient instance.
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    # --- Library browsing ---------------------------------------------------

    def list_sections(self) -> list[LibrarySection]:
        """List all library sections on the server."""
        sections = self._client.server.library.sections()
        return [
            LibrarySection(
                key=str(s.key),
                title=s.title,
                section_type=MediaType.from_plex_type(s.type),
                count=getattr(s, "totalSize", 0),
            )
            for s in sections
        ]

    def get_section(self, title: str) -> LibrarySection | None:
        """Find a library section by title."""
        for section in self.list_sections():
            if section.title.lower() == title.lower():
                return section
        return None

    # --- Metadata reading --------------------------------------------------

    def get_all_movies(self, section_title: str = "Movies") -> list[MediaMetadata]:
        """Retrieve all movies from a library section."""
        section = self._client.server.library.section(section_title)
        movies = section.all()
        return [self._movie_to_metadata(m) for m in movies]

    def get_all_shows(self, section_title: str = "TV Shows") -> list[MediaMetadata]:
        """Retrieve all shows from a library section."""
        section = self._client.server.library.section(section_title)
        shows = section.all()
        return [self._show_to_metadata(s) for s in shows]

    def search(
        self,
        query: str,
        section_title: str | None = None,
        media_type: MediaType | None = None,
    ) -> list[MediaMetadata]:
        """Search for media items by title.

        Args:
            query: Search string.
            section_title: Optional library section to limit search.
            media_type: Optional media type filter.

        Returns:
            List of matching MediaMetadata items.
        """
        kwargs: dict[str, Any] = {"query": query}
        if media_type:
            kwargs["mediatype"] = media_type.value
        if section_title:
            section = self.get_section(section_title)
            if section:
                kwargs["sectionId"] = int(section.key)

        results = self._client.server.search(**kwargs)  # type: ignore[no-untyped-call]
        metadata: list[MediaMetadata] = []
        for item in results:
            if isinstance(item, Movie):
                metadata.append(self._movie_to_metadata(item))
            elif isinstance(item, Show):
                metadata.append(self._show_to_metadata(item))
        return metadata

    def get_metadata(self, rating_key: str | int) -> MediaMetadata | None:
        """Fetch and convert metadata for a single item by rating key.

        Args:
            rating_key: Plex rating key for the item.

        Returns:
            MediaMetadata if found, None for unsupported types.
        """
        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        if isinstance(item, Movie):
            return self._movie_to_metadata(item)
        if isinstance(item, Show):
            return self._show_to_metadata(item)
        if isinstance(item, Episode):
            return self._episode_to_metadata(item)
        if isinstance(item, Season):
            return self._season_to_metadata(item)
        return None

    # --- Metadata writing --------------------------------------------------

    def edit_metadata(
        self,
        rating_key: str | int,
        edits: list[MetadataEdit],
    ) -> MediaMetadata:
        """Apply metadata edits to a single item.

        Args:
            rating_key: Plex rating key for the item.
            edits: List of field-value pairs to update.

        Returns:
            Updated metadata after edit.
        """
        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        edit_dict = {e.field: e.value for e in edits}
        item.edit(**edit_dict)
        item.reload()
        if isinstance(item, Movie):
            return self._movie_to_metadata(item)
        if isinstance(item, Show):
            return self._show_to_metadata(item)
        msg = f"Unsupported media type: {type(item).__name__}"
        raise ValueError(msg)

    def batch_edit(
        self,
        rating_keys: list[str | int],
        edits: list[MetadataEdit],
    ) -> BatchEditResult:
        """Apply the same edits to multiple items.

        Args:
            rating_keys: List of Plex rating keys.
            edits: List of field-value pairs to apply to each item.

        Returns:
            Summary of successful and failed edits.
        """
        result = BatchEditResult(total=len(rating_keys))
        for key in rating_keys:
            try:
                self.edit_metadata(key, edits)
                result.updated += 1
            except Exception as exc:
                result.failed += 1
                result.errors[str(key)] = str(exc)
                logger.warning("Failed to edit item %s: %s", key, exc)
        return result

    # --- Tag operations -----------------------------------------------------

    def add_tag(
        self,
        rating_key: str | int,
        tag_type: str,
        values: list[str],
        locked: bool = True,
    ) -> MediaMetadata | None:
        """Add tag(s) to a media item.

        Args:
            rating_key: Plex rating key for the item.
            tag_type: One of 'genre', 'collection', 'label', 'director',
                'writer', 'mood', 'style', 'country', 'similar_artist'.
            values: List of tag string values to add.
            locked: Whether to lock the field after adding.

        Returns:
            Updated metadata, or None for unsupported types.

        Raises:
            ValueError: If tag_type is not recognized.
        """
        method_name = _TAG_ADD_METHODS.get(tag_type)
        if method_name is None:
            valid = ", ".join(sorted(_TAG_ADD_METHODS))
            msg = f"Unknown tag type '{tag_type}'. Valid types: {valid}"
            raise ValueError(msg)

        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        add_method = getattr(item, method_name)
        add_method(values, locked=locked)
        item.reload()
        return self._to_metadata(item)

    def remove_tag(
        self,
        rating_key: str | int,
        tag_type: str,
        values: list[str],
        locked: bool = True,
    ) -> MediaMetadata | None:
        """Remove tag(s) from a media item.

        Args:
            rating_key: Plex rating key for the item.
            tag_type: One of 'genre', 'collection', 'label', 'director',
                'writer', 'mood', 'style', 'country', 'similar_artist'.
            values: List of tag string values to remove.
            locked: Whether to lock the field after removing.

        Returns:
            Updated metadata, or None for unsupported types.

        Raises:
            ValueError: If tag_type is not recognized.
        """
        method_name = _TAG_REMOVE_METHODS.get(tag_type)
        if method_name is None:
            valid = ", ".join(sorted(_TAG_REMOVE_METHODS))
            msg = f"Unknown tag type '{tag_type}'. Valid types: {valid}"
            raise ValueError(msg)

        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        remove_method = getattr(item, method_name)
        remove_method(values, locked=locked)
        item.reload()
        return self._to_metadata(item)

    # --- Field lock/unlock --------------------------------------------------

    def lock_field(
        self,
        rating_key: str | int,
        fields: list[str],
    ) -> MediaMetadata | None:
        """Lock metadata field(s) on a media item.

        Locking prevents Plex from automatically overwriting the field
        value during metadata refreshes.

        Args:
            rating_key: Plex rating key for the item.
            fields: List of field names to lock (e.g. 'title', 'summary', 'year').

        Returns:
            Updated metadata, or None for unsupported types.
        """
        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        edit_dict = {f"{field}.locked": 1 for field in fields}
        item.edit(**edit_dict)
        item.reload()
        return self._to_metadata(item)

    def unlock_field(
        self,
        rating_key: str | int,
        fields: list[str],
    ) -> MediaMetadata | None:
        """Unlock metadata field(s) on a media item.

        Unlocking allows Plex to automatically update the field
        value during metadata refreshes.

        Args:
            rating_key: Plex rating key for the item.
            fields: List of field names to unlock (e.g. 'title', 'summary', 'year').

        Returns:
            Updated metadata, or None for unsupported types.
        """
        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        edit_dict = {f"{field}.locked": 0 for field in fields}
        item.edit(**edit_dict)
        item.reload()
        return self._to_metadata(item)

    # --- Collections -------------------------------------------------------

    def list_collections(self, section_title: str = "Movies") -> list[CollectionInfo]:
        """List all collections in a library section."""
        section = self._client.server.library.section(section_title)
        collections = section.collections()
        return [
            CollectionInfo(
                key=c.key,
                title=c.title,
                smart=getattr(c, "smart", False),
                content_count=getattr(c, "childCount", 0),
                section_title=section_title,
            )
            for c in collections
        ]

    # --- Private helpers ---------------------------------------------------

    # --- Subtitle operations ------------------------------------------------

    def search_subtitles(
        self,
        rating_key: str | int,
        language: str = "en",
        hearing_impaired: int = 0,
        forced: int = 0,
    ) -> list[SubtitleStreamInfo]:
        """Search for available subtitles for a media item.

        Args:
            rating_key: Plex rating key of the item.
            language: ISO 639-1 language code (default: 'en').
            hearing_impaired: 0=prefer non-SDH, 1=prefer SDH,
                              2=only SDH, 3=only non-SDH.
            forced: 0=prefer non-forced, 1=prefer forced,
                    2=only forced, 3=only non-forced.

        Returns:
            List of SubtitleStreamInfo objects.
        """
        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        streams = item.searchSubtitles(
            language=language, hearingImpaired=hearing_impaired, forced=forced
        )
        return [self._subtitle_stream_to_info(s) for s in streams]

    def download_subtitle(self, rating_key: str | int, stream_id: int) -> bool:
        """Download (apply) a subtitle stream to a media item.

        Finds the subtitle stream by ID and downloads it. The subtitle
        will be applied asynchronously by the Plex server.

        Args:
            rating_key: Plex rating key of the item.
            stream_id: ID of the subtitle stream to download.

        Returns:
            True if the download request was accepted.

        Raises:
            ValueError: If no subtitle stream with the given ID is found.
        """
        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        streams = item.subtitleStreams()
        for stream in streams:
            if stream.id == stream_id:
                item.downloadSubtitles(stream)
                return True
        # Also check search results (on-demand subtitles not yet downloaded)
        search_results = item.searchSubtitles()
        for stream in search_results:
            if stream.id == stream_id:
                item.downloadSubtitles(stream)
                return True
        msg = f"Subtitle stream with ID {stream_id} not found on item {key}"
        raise ValueError(msg)

    def upload_subtitle(self, rating_key: str | int, filepath: str) -> bool:
        """Upload a subtitle file for a media item.

        Args:
            rating_key: Plex rating key of the item.
            filepath: Local path to subtitle file (.srt, .ass, etc.).

        Returns:
            True if upload was successful.
        """
        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        item.uploadSubtitles(filepath)
        return True

    def remove_subtitle(
        self,
        rating_key: str | int,
        stream_id: int | None = None,
        stream_title: str | None = None,
    ) -> bool:
        """Remove a subtitle from a media item.

        Provide either stream_id or stream_title to identify the
        subtitle to remove. If neither is provided, raises ValueError.

        Args:
            rating_key: Plex rating key of the item.
            stream_id: ID of the subtitle stream to remove.
            stream_title: Title of the subtitle stream to remove.

        Returns:
            True if removal was successful.

        Raises:
            ValueError: If neither stream_id nor stream_title is provided.
        """
        if stream_id is None and stream_title is None:
            msg = "Either stream_id or stream_title must be provided"
            raise ValueError(msg)

        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        item.removeSubtitles(streamID=stream_id, streamTitle=stream_title)
        return True

    # --- Private helpers ---------------------------------------------------

    @staticmethod
    def _subtitle_stream_to_info(stream: object) -> SubtitleStreamInfo:
        """Convert a plexapi SubtitleStream to our SubtitleStreamInfo model."""
        return SubtitleStreamInfo(
            id=stream.id,
            language=getattr(stream, "language", "") or "",
            language_code=getattr(stream, "languageCode", "") or "",
            language_tag=getattr(stream, "languageTag", "") or "",
            title=getattr(stream, "title", "") or "",
            display_title=getattr(stream, "displayTitle", "") or "",
            extended_display_title=getattr(stream, "extendedDisplayTitle", "") or "",
            codec=getattr(stream, "codec", "") or "",
            format=getattr(stream, "format", "") or "",
            forced=bool(getattr(stream, "forced", False)),
            hearing_impaired=bool(getattr(stream, "hearingImpaired", False)),
            score=getattr(stream, "score", None),
            provider=getattr(stream, "providerTitle", "") or "",
            key=getattr(stream, "key", "") or "",
            selected=bool(getattr(stream, "selected", False)),
            can_auto_sync=bool(getattr(stream, "canAutoSync", False)),
            perfect_match=bool(getattr(stream, "perfectMatch", False)),
            user_id=getattr(stream, "userID", None),
        )

    def _to_metadata(
        self, item: Movie | Show | Episode | Season
    ) -> MediaMetadata | None:
        """Convert a plexapi item to MediaMetadata based on its type.

        Delegates to the appropriate type-specific converter.
        Returns None for unsupported types.
        """
        if isinstance(item, Movie):
            return self._movie_to_metadata(item)
        if isinstance(item, Show):
            return self._show_to_metadata(item)
        if isinstance(item, Episode):
            return self._episode_to_metadata(item)
        if isinstance(item, Season):
            return self._season_to_metadata(item)
        return None

    @staticmethod
    def _movie_to_metadata(movie: Movie) -> MediaMetadata:
        """Convert a plexapi Movie to our MediaMetadata model."""
        return MediaMetadata(
            key=str(movie.ratingKey),
            title=movie.title,
            original_title=getattr(movie, "originalTitle", None),
            sort_title=getattr(movie, "titleSort", None),
            summary=movie.summary or None,
            year=int(movie.year) if movie.year else None,
            originally_available=getattr(movie, "originallyAvailableAt", None),
            rating=movie.rating,
            audience_rating=movie.audienceRating,
            content_rating=movie.contentRating,
            studio=getattr(movie, "studio", None),
            tagline=getattr(movie, "tagline", None),
            media_type=MediaType.MOVIE,
        )

    @staticmethod
    def _show_to_metadata(show: Show) -> MediaMetadata:
        """Convert a plexapi Show to our MediaMetadata model."""
        return MediaMetadata(
            key=str(show.ratingKey),
            title=show.title,
            original_title=getattr(show, "originalTitle", None),
            sort_title=getattr(show, "titleSort", None),
            summary=show.summary or None,
            year=int(show.year) if show.year else None,
            originally_available=getattr(show, "originallyAvailableAt", None),
            rating=show.rating,
            audience_rating=show.audienceRating,
            content_rating=show.contentRating,
            studio=getattr(show, "studio", None),
            tagline=None,
            media_type=MediaType.SHOW,
        )

    @staticmethod
    def _episode_to_metadata(episode: Episode) -> MediaMetadata:
        """Convert a plexapi Episode to our MediaMetadata model."""
        return MediaMetadata(
            key=str(episode.ratingKey),
            title=episode.title,
            sort_title=getattr(episode, "titleSort", None),
            summary=episode.summary or None,
            year=int(episode.year) if episode.year else None,
            originally_available=getattr(episode, "originallyAvailableAt", None),
            media_type=MediaType.EPISODE,
        )

    @staticmethod
    def _season_to_metadata(season: Season) -> MediaMetadata:
        """Convert a plexapi Season to our MediaMetadata model."""
        return MediaMetadata(
            key=str(season.ratingKey),
            title=season.title,
            summary=season.summary or None,
            year=int(season.year) if season.year else None,
            originally_available=getattr(season, "originallyAvailableAt", None),
            media_type=MediaType.SEASON,
        )
